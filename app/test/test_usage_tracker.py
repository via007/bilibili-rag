"""
test_usage_tracker.py — 测试 UsageTrackingCallback.on_llm_end() 的各种路径
以及 _extract_token_usage() 的流式/非流式兼容逻辑。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult, ChatGeneration

from app.services.llm.usage_tracker import UsageTrackingCallback, _extract_token_usage


def _make_llm_result(prompt_tokens: int, completion_tokens: int, total_tokens: int) -> LLMResult:
    """构造带 token_usage 的 LLMResult（非流式路径）"""
    return LLMResult(
        generations=[[]],
        llm_output={
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        },
    )


def _make_llm_result_no_usage() -> LLMResult:
    """构造不包含 token_usage 的 LLMResult"""
    return LLMResult(
        generations=[[]],
        llm_output={"some_other_key": "value"},
    )


def _make_llm_result_null_output() -> LLMResult:
    """构造 llm_output 为 None 的 LLMResult"""
    return LLMResult(
        generations=[[]],
        llm_output=None,
    )


def _make_llm_result_streaming(
    input_tokens: int, output_tokens: int, total_tokens: int = 0
) -> LLMResult:
    """构造流式路径的 LLMResult — llm_output=None，usage_metadata 在 message 上"""
    tt = total_tokens or input_tokens + output_tokens
    msg = AIMessage(content="test response", usage_metadata={
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": tt,
    })
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]], llm_output=None)


# ═══════════════════════════════════════════════════════════════
# _extract_token_usage 单元测试
# ═══════════════════════════════════════════════════════════════

class TestExtractTokenUsage:
    """_extract_token_usage() 函数：兼容流式与非流式两种路径"""

    def test_llm_output_path(self):
        """非流式：llm_output.token_usage 有值时优先使用"""
        response = _make_llm_result(100, 50, 150)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (100, 50, 150, "llm_output")

    def test_usage_metadata_path(self):
        """流式：llm_output=None 时从 usage_metadata 提取"""
        response = _make_llm_result_streaming(200, 80, 280)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (200, 80, 280, "usage_metadata")

    def test_usage_metadata_total_from_parts(self):
        """流式：total_tokens 未提供时从 input+output 计算"""
        response = _make_llm_result_streaming(50, 30, 0)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (50, 30, 80, "usage_metadata")

    def test_llm_output_priority(self):
        """llm_output 和 usage_metadata 同时存在时优先 llm_output"""
        msg = AIMessage(content="test", usage_metadata={
            "input_tokens": 999, "output_tokens": 999, "total_tokens": 1998,
        })
        gen = ChatGeneration(message=msg)
        response = LLMResult(
            generations=[[gen]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                }
            },
        )
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (10, 20, 30, "llm_output")

    def test_both_empty(self):
        """llm_output=None 且 generations 为空时返回 (0,0,0,'none')"""
        response = LLMResult(generations=[[]], llm_output=None)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (0, 0, 0, "none")

    def test_usage_metadata_zero_tokens(self):
        """usage_metadata 中 total_tokens=0 时返回 (0,0,0,'none')"""
        msg = AIMessage(content="test", usage_metadata={
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        })
        gen = ChatGeneration(message=msg)
        response = LLMResult(generations=[[gen]], llm_output=None)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (0, 0, 0, "none")

    def test_no_usage_metadata_attr(self):
        """message 上没有 usage_metadata 属性时返回 none"""
        msg = AIMessage(content="test")  # 无 usage_metadata
        gen = ChatGeneration(message=msg)
        response = LLMResult(generations=[[gen]], llm_output=None)
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (0, 0, 0, "none")

    def test_llm_output_token_usage_is_none(self):
        """llm_output 存在但 token_usage 为 None → 回退到 usage_metadata"""
        msg = AIMessage(content="test", usage_metadata={
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
        })
        gen = ChatGeneration(message=msg)
        response = LLMResult(
            generations=[[gen]],
            llm_output={"token_usage": None},
        )
        p, c, t, src = _extract_token_usage(response)
        assert (p, c, t, src) == (10, 5, 15, "usage_metadata")


# ═══════════════════════════════════════════════════════════════
# 流式路径 on_llm_end 回调测试（usage_metadata）
# ═══════════════════════════════════════════════════════════════

class TestOnLlmEndStreamingPath:
    """流式调用（astream）时 token 用量来自 usage_metadata"""

    @pytest.fixture
    def writer_mock(self):
        mock = AsyncMock()
        mock.enqueue = AsyncMock()
        return mock

    @pytest.fixture
    def tracker(self, writer_mock):
        return UsageTrackingCallback(
            session_id="streaming-session",
            credential_id=7,
            provider="openai",
            model="gpt-4o",
            writer=writer_mock,
        )

    @pytest.mark.asyncio
    async def test_streaming_result_enqueues(self, tracker, writer_mock):
        """流式 LLMResult（llm_output=None, usage_metadata 有值）正确入队"""
        response = _make_llm_result_streaming(200, 80, 280)
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert writer_mock.enqueue.called
        kwargs = writer_mock.enqueue.call_args.kwargs
        assert kwargs["prompt_tokens"] == 200
        assert kwargs["completion_tokens"] == 80
        assert kwargs["total_tokens"] == 280
        assert kwargs["session_id"] == "streaming-session"
        assert kwargs["credential_id"] == 7

    @pytest.mark.asyncio
    async def test_streaming_null_output_still_enqueues(self, tracker, writer_mock):
        """流式路径：llm_output=None 但 usage_metadata 有值时仍应入队"""
        response = _make_llm_result_streaming(50, 30)
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert writer_mock.enqueue.called
        kwargs = writer_mock.enqueue.call_args.kwargs
        assert kwargs["total_tokens"] == 80

    @pytest.mark.asyncio
    async def test_streaming_zero_usage_skips(self, tracker, writer_mock):
        """流式路径但 usage_metadata 全零时跳过"""
        response = _make_llm_result_streaming(0, 0, 0)
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert not writer_mock.enqueue.called


class TestOnLlmEndWithWriter:
    """有 writer 时，on_llm_end 正常入队到缓冲区"""

    @pytest.fixture
    def writer_mock(self):
        mock = AsyncMock()
        mock.enqueue = AsyncMock()
        return mock

    @pytest.fixture
    def tracker(self, writer_mock):
        return UsageTrackingCallback(
            session_id="test-session",
            credential_id=42,
            provider="anthropic",
            model="claude-opus",
            writer=writer_mock,
        )

    @pytest.mark.asyncio
    async def test_valid_data_enqueues(self, tracker, writer_mock):
        """有效 token 数据被正确入队（fire-and-forget via ensure_future）"""
        response = _make_llm_result(100, 50, 150)
        tracker.on_llm_end(response)

        # fire-and-forget 异步入队，等待一下
        await asyncio.sleep(0.1)

        assert writer_mock.enqueue.called
        call_kwargs = writer_mock.enqueue.call_args.kwargs
        assert call_kwargs["session_id"] == "test-session"
        assert call_kwargs["credential_id"] == 42
        assert call_kwargs["provider"] == "anthropic"
        assert call_kwargs["model"] == "claude-opus"
        assert call_kwargs["prompt_tokens"] == 100
        assert call_kwargs["completion_tokens"] == 50
        assert call_kwargs["total_tokens"] == 150
        assert call_kwargs["api_calls"] == 1

    @pytest.mark.asyncio
    async def test_zero_tokens_skips(self, tracker, writer_mock):
        """total_tokens 为 0 时静默跳过，不入队"""
        response = _make_llm_result(0, 0, 0)
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert not writer_mock.enqueue.called

    @pytest.mark.asyncio
    async def test_missing_llm_output_no_crash(self, tracker, writer_mock):
        """llm_output 为 None 时不崩溃"""
        response = _make_llm_result_null_output()
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        # llm_output is None → token_usage {} → total_tokens 0 → skip
        assert not writer_mock.enqueue.called

    @pytest.mark.asyncio
    async def test_no_token_usage_key_no_crash(self, tracker, writer_mock):
        """llm_output 不包含 token_usage 时不崩溃"""
        response = _make_llm_result_no_usage()
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert not writer_mock.enqueue.called

    @pytest.mark.asyncio
    async def test_total_tokens_from_parts_when_missing(self, tracker, writer_mock):
        """当 total_tokens 未提供时，从 prompt_tokens + completion_tokens 计算"""
        response = LLMResult(
            generations=[[]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 40,
                    # total_tokens 未提供
                }
            },
        )
        tracker.on_llm_end(response)

        await asyncio.sleep(0.1)
        assert writer_mock.enqueue.called
        call_kwargs = writer_mock.enqueue.call_args.kwargs
        assert call_kwargs["total_tokens"] == 120  # 80 + 40


class TestOnLlmEndNoWriter:
    """无 writer 时，on_llm_end 降级为日志警告不崩溃"""

    @pytest.fixture
    def tracker_no_writer(self):
        return UsageTrackingCallback(
            session_id="test-session",
            credential_id=None,
            provider="openai",
            model="gpt-4",
            writer=None,
        )

    def test_no_writer_no_crash(self, tracker_no_writer):
        """无 writer 时有 token 用量也不崩溃，仅输出 warning 日志"""
        response = _make_llm_result(100, 50, 150)
        tracker_no_writer.on_llm_end(response)  # 不应抛异常

    def test_no_writer_zero_tokens_no_crash(self, tracker_no_writer):
        """无 writer 且零 token，静默跳过"""
        response = _make_llm_result(0, 0, 0)
        tracker_no_writer.on_llm_end(response)  # 不应抛异常

    def test_no_writer_null_output_no_crash(self, tracker_no_writer):
        """无 writer 且 llm_output=None，不崩溃"""
        response = _make_llm_result_null_output()
        tracker_no_writer.on_llm_end(response)


class TestOnLlmEndExceptionSafety:
    """异常安全性测试：回调内部异常不传播到调用方"""

    @pytest.mark.asyncio
    async def test_enqueue_exception_not_propagated(self):
        """writer.enqueue 内部抛异常时不传播到 on_llm_end 调用方"""
        writer = AsyncMock()
        writer.enqueue = MagicMock(side_effect=RuntimeError("mock failure"))

        tracker = UsageTrackingCallback(
            session_id="test-session",
            writer=writer,
        )
        response = _make_llm_result(100, 50, 150)

        # 不应抛出异常
        tracker.on_llm_end(response)
        # 注意：UsageTrackingCallback 的 try/except 捕获了 Exception，
        # 但 fire-and-forget 通过 asyncio.ensure_future 启动的协程异常
        # 不会被 on_llm_end 的 try/except 捕获。
        # 这是预期行为 —— 异常只会记录到 asyncio 日志，不会传播。


# ═══════════════════════════════════════════════════════════════
# 端到端集成测试：on_llm_end → enqueue → flush → DB
# ═══════════════════════════════════════════════════════════════

class TestEndToEndUsageStorage:
    """全链路：tracker 回调 → 即时写入 → credential_usage 表"""

    @staticmethod
    def _patch_session_factory(test_db):
        """让 enqueue() 内部使用的 async_session_factory 返回 test_db"""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=test_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        return patch(
            "app.services.llm.buffered_usage_writer.async_session_factory",
            return_value=mock_ctx,
        )

    @pytest.mark.asyncio
    async def test_non_streaming_full_chain(self, test_db):
        """非流式路径：llm_output.token_usage → enqueue 即时写入 DB"""
        from sqlalchemy import select
        from app.models import CredentialUsage
        from app.repository.usage_repository import UsageRepository
        from app.services.llm.buffered_usage_writer import BufferedUsageWriter

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        tracker = UsageTrackingCallback(
            session_id="e2e-nonstream",
            credential_id=42,
            provider="deepseek",
            model="deepseek-v3",
            writer=writer,
        )

        # 模拟非流式 LLM 调用完成
        response = _make_llm_result(300, 150, 450)

        # enqueue 即时写入 → 需要 patch session factory 指向 test_db
        with self._patch_session_factory(test_db):
            tracker.on_llm_end(response)
            # 等待 fire-and-forget enqueue 完成
            await asyncio.sleep(0.15)

        # 即时写入模式，pending_count 始终为 0
        assert writer.pending_count == 0

        # 验证数据库
        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "e2e-nonstream"
        assert row.credential_id == 42
        assert row.provider == "deepseek"
        assert row.model == "deepseek-v3"
        assert row.prompt_tokens == 300
        assert row.completion_tokens == 150
        assert row.total_tokens == 450
        assert row.api_calls == 1

    @pytest.mark.asyncio
    async def test_streaming_full_chain(self, test_db):
        """流式路径：usage_metadata → enqueue 即时写入 DB（修复核心场景）"""
        from sqlalchemy import select
        from app.models import CredentialUsage
        from app.repository.usage_repository import UsageRepository
        from app.services.llm.buffered_usage_writer import BufferedUsageWriter

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        tracker = UsageTrackingCallback(
            session_id="e2e-stream",
            credential_id=None,  # 系统默认 Key
            provider="openai",
            model="gpt-4o",
            writer=writer,
        )

        # 模拟流式 LLM 调用完成（关键场景：llm_output=None）
        response = _make_llm_result_streaming(500, 200, 700)

        with self._patch_session_factory(test_db):
            tracker.on_llm_end(response)
            await asyncio.sleep(0.15)

        assert writer.pending_count == 0

        # 验证数据库
        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "e2e-stream"
        assert row.credential_id is None
        assert row.provider == "openai"
        assert row.model == "gpt-4o"
        assert row.prompt_tokens == 500
        assert row.completion_tokens == 200
        assert row.total_tokens == 700
        assert row.api_calls == 1

    @pytest.mark.asyncio
    async def test_mixed_stream_and_non_stream(self, test_db):
        """混合调用：多次 enqueue 即时写入，所有记录正确写入"""
        from sqlalchemy import select
        from app.models import CredentialUsage
        from app.repository.usage_repository import UsageRepository
        from app.services.llm.buffered_usage_writer import BufferedUsageWriter

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        tracker = UsageTrackingCallback(
            session_id="e2e-mixed",
            provider="openai",
            model="gpt-4o",
            writer=writer,
        )

        # 一次非流式 + 一次流式
        with self._patch_session_factory(test_db):
            tracker.on_llm_end(_make_llm_result(100, 50, 150))
            tracker.on_llm_end(_make_llm_result_streaming(200, 100, 300))
            await asyncio.sleep(0.15)

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 2

        total = sum(r.total_tokens for r in rows)
        assert total == 450  # 150 + 300


class TestTrackerInitDefaults:
    """测试构造函数默认值和属性存储"""

    def test_defaults(self):
        tracker = UsageTrackingCallback(session_id="sid")
        assert tracker.session_id == "sid"
        assert tracker.credential_id is None
        assert tracker.provider == "openai"
        assert tracker.model is None
        assert tracker._writer is None

    def test_explicit_values(self):
        writer_mock = MagicMock()
        tracker = UsageTrackingCallback(
            session_id="sid",
            credential_id=99,
            provider="deepseek",
            model="deepseek-v3",
            writer=writer_mock,
        )
        assert tracker.session_id == "sid"
        assert tracker.credential_id == 99
        assert tracker.provider == "deepseek"
        assert tracker.model == "deepseek-v3"
        assert tracker._writer is writer_mock
