"""
即时用量写入器

每条 LLM 用量记录到达时立即写入数据库（不缓冲、不定时）。
on_llm_end 通过 asyncio.ensure_future 触发，不阻塞 LLM 响应流。
"""
import time
from typing import Optional

from loguru import logger

from app.repository.usage_repository import UsageRepository, get_usage_repository
from app.database import async_session_factory


class BufferedUsageWriter:
    """即时写入器：每条 enqueue 立即 _do_flush 写入数据库"""

    def __init__(
        self,
        usage_repo: Optional[UsageRepository] = None,
        flush_interval: int = 30,   # 不再使用，保留签名兼容
        batch_size: int = 50,       # 不再使用，保留签名兼容
    ):
        self._repo = usage_repo or get_usage_repository()

    async def start(self) -> None:
        """兼容旧调用方（无操作）"""
        logger.info("[USAGE_WRITER] immediate-write mode (no timer)")

    async def enqueue(self, **record) -> None:
        """入队一条用量记录并立即写入数据库。"""
        logger.info(
            f"[USAGE_WRITER] writing record: "
            f"tokens={record.get('total_tokens', 0)} "
            f"provider={record.get('provider', '?')}"
        )

        start = time.time()
        try:
            async with async_session_factory() as db:
                await self._repo.batch_record([record], db)
            elapsed = (time.time() - start) * 1000
            logger.info(
                f"[USAGE_WRITER] written {record.get('total_tokens', 0)} tokens "
                f"in {elapsed:.0f}ms"
            )
        except Exception as e:
            logger.error(f"[USAGE_WRITER] write failed: {e}")

    async def shutdown(self) -> None:
        """优雅关闭（即时模式下写空操作）"""
        logger.info("[USAGE_WRITER] shutdown complete")

    @property
    def pending_count(self) -> int:
        """即时模式下始终为 0"""
        return 0


# 模块级单例
_writer: Optional[BufferedUsageWriter] = None


def get_buffered_usage_writer() -> BufferedUsageWriter:
    """获取 BufferedUsageWriter 单例"""
    global _writer
    if _writer is None:
        _writer = BufferedUsageWriter()
    return _writer


async def start_buffered_usage_writer() -> BufferedUsageWriter:
    """启动全局 writer 单例（在 lifespan startup 中调用）"""
    writer = get_buffered_usage_writer()
    await writer.start()
    return writer


async def shutdown_buffered_usage_writer() -> None:
    """关闭全局 writer 单例（在 lifespan shutdown 中调用）"""
    global _writer
    if _writer is not None:
        await _writer.shutdown()
        _writer = None
