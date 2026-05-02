"""
用量追踪回调 — 通过 LangChain BaseCallbackHandler 记录每次 LLM 调用的 token 消耗。

用法：
    writer = get_buffered_usage_writer()
    tracker = UsageTrackingCallback(session_id, credential_id, provider, model, writer)
    llm = ChatOpenAI(...)
    llm.callbacks = [tracker]

数据流：
    on_llm_end → 提取 token_usage → fire-and-forget enqueue 到 BufferedUsageWriter
    BufferedUsageWriter 后台协程 → 定时/定量批量 INSERT → credential_usage 表

两种 token_usage 来源：
    - 非流式 (ainvoke)：llm_output["token_usage"] (prompt_tokens/completion_tokens/total_tokens)
    - 流式 (astream)  ：generations[0][0].message.usage_metadata (input_tokens/output_tokens/total_tokens)
"""
import asyncio
from typing import Optional, Any, TYPE_CHECKING

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from loguru import logger

if TYPE_CHECKING:
    from app.services.llm.buffered_usage_writer import BufferedUsageWriter


def _extract_token_usage(response: LLMResult) -> tuple[int, int, int, str]:
    """
    从 LLMResult 中提取 token 用量，兼容流式和非流式两种路径。

    返回 (prompt_tokens, completion_tokens, total_tokens, source)
    source: "llm_output" | "usage_metadata" | "none"
    """
    # 路径 1: 非流式 — llm_output["token_usage"]
    if response.llm_output:
        tu = response.llm_output.get("token_usage")
        if tu and isinstance(tu, dict):
            p = tu.get("prompt_tokens", 0)
            c = tu.get("completion_tokens", 0)
            t = tu.get("total_tokens", p + c)
            if t > 0:
                return p, c, t, "llm_output"

    # 路径 2: 流式 — generations[0][0].message.usage_metadata
    # (TypedDict: input_tokens / output_tokens / total_tokens)
    try:
        gen = response.generations[0][0]
        msg = gen.message
        um = getattr(msg, "usage_metadata", None) or {}
        if um:
            p = um.get("input_tokens", 0)
            c = um.get("output_tokens", 0)
            t = um.get("total_tokens", p + c)
            if t > 0:
                return p, c, t, "usage_metadata"
    except (IndexError, AttributeError, TypeError):
        pass

    return 0, 0, 0, "none"


class UsageTrackingCallback(BaseCallbackHandler):
    """
    LangChain 回调 — 在 on_llm_end 中提取 token_usage 并入队至缓冲写入器。

    - 无 writer 时静默跳过（兼容降级）
    - 有 writer 时 fire-and-forget enqueue，不阻塞 LLM 响应流
    - 实际数据库写入由 BufferedUsageWriter 的后台协程负责
    """

    def __init__(
        self,
        session_id: str,
        credential_id: Optional[int] = None,
        provider: str = "openai",
        model: Optional[str] = None,
        writer: Optional["BufferedUsageWriter"] = None,
    ):
        self.session_id = session_id
        self.credential_id = credential_id
        self.provider = provider
        self.model = model
        self._writer = writer

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 调用完成后触发，提取 token 用量并入队到缓冲写入器。"""
        try:
            prompt_tokens, completion_tokens, total_tokens, source = _extract_token_usage(response)

            logger.info(
                f"[USAGE_TRACKER] on_llm_end fired "
                f"prompt={prompt_tokens} completion={completion_tokens} "
                f"total={total_tokens} source={source} "
                f"provider={self.provider} model={self.model}"
            )

            if total_tokens == 0:
                llm_output_keys = (
                    list(response.llm_output.keys()) if response.llm_output
                    else "None"
                )
                logger.warning(
                    f"[USAGE_TRACKER] total_tokens=0, skipping enqueue "
                    f"(llm_output={llm_output_keys}, "
                    f"source={source})"
                )
                return

            # 有 writer 时入队到缓冲批量写入器
            if self._writer is not None:
                asyncio.ensure_future(
                    self._writer.enqueue(
                        session_id=self.session_id,
                        credential_id=self.credential_id,
                        provider=self.provider,
                        model=self.model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        api_calls=1,
                    )
                )
            else:
                # 降级：无 writer 时至少记录日志
                logger.warning(
                    f"[USAGE_TRACKER] no writer available, "
                    f"usage not recorded: {total_tokens} tokens"
                )

            logger.info(
                f"[USAGE_TRACKER] enqueued {total_tokens} tokens "
                f"(prompt={prompt_tokens}, completion={completion_tokens}) "
                f"provider={self.provider} model={self.model}"
            )
        except Exception as e:
            logger.error(f"[USAGE_TRACKER] failed to enqueue usage: {e}")
