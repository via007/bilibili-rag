"""
test_usage_writer.py — 测试即时写入 BufferedUsageWriter
（enqueue → 立即 flush → DB）
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm.buffered_usage_writer import (
    BufferedUsageWriter,
    get_buffered_usage_writer,
)
from app.repository.usage_repository import UsageRepository


class TestEnqueueImmediateWrite:
    """enqueue() 立即写入数据库"""

    @pytest.mark.asyncio
    async def test_enqueue_writes_immediately(self, test_db):
        """enqueue 后立即写入 DB，无缓冲"""
        from sqlalchemy import select
        from app.models import CredentialUsage

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        with patch(
            "app.services.llm.buffered_usage_writer.async_session_factory"
        ) as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=test_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_ctx

            await writer.enqueue(
                session_id="s1",
                credential_id=5,
                provider="openai",
                model="gpt-4",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                api_calls=1,
            )

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "s1"
        assert row.credential_id == 5
        assert row.provider == "openai"
        assert row.model == "gpt-4"
        assert row.prompt_tokens == 100
        assert row.completion_tokens == 50
        assert row.total_tokens == 150
        assert row.api_calls == 1

    @pytest.mark.asyncio
    async def test_multiple_enqueues_each_write(self, test_db):
        """多次 enqueue，每次单独写入"""
        from sqlalchemy import select, func
        from app.models import CredentialUsage

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        with patch(
            "app.services.llm.buffered_usage_writer.async_session_factory"
        ) as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=test_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_ctx

            await writer.enqueue(session_id="s1", total_tokens=100)
            await writer.enqueue(session_id="s1", total_tokens=200)

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 2
        total = sum(r.total_tokens for r in rows)
        assert total == 300

    @pytest.mark.asyncio
    async def test_enqueue_handles_null_credential(self, test_db):
        """credential_id=None 时正确写入"""
        from sqlalchemy import select
        from app.models import CredentialUsage

        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        with patch(
            "app.services.llm.buffered_usage_writer.async_session_factory"
        ) as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=test_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_ctx

            await writer.enqueue(
                session_id="s1",
                credential_id=None,
                provider="openai",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                api_calls=1,
            )

        result = await test_db.execute(select(CredentialUsage))
        row = result.scalars().first()
        assert row.credential_id is None
        assert row.total_tokens == 15


class TestPendingCount:
    """即时模式下 pending_count 始终为 0"""

    def test_pending_count_zero(self):
        writer = BufferedUsageWriter()
        assert writer.pending_count == 0

    @pytest.mark.asyncio
    async def test_pending_count_stays_zero_after_enqueue(self, test_db):
        repo = UsageRepository()
        writer = BufferedUsageWriter(usage_repo=repo)

        with patch(
            "app.services.llm.buffered_usage_writer.async_session_factory"
        ) as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=test_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_ctx

            await writer.enqueue(session_id="s1", total_tokens=100)

        assert writer.pending_count == 0


class TestStartAndShutdown:
    """start/shutdown 兼容旧接口"""

    @pytest.mark.asyncio
    async def test_start_noop(self):
        writer = BufferedUsageWriter()
        await writer.start()

    @pytest.mark.asyncio
    async def test_shutdown_noop(self):
        writer = BufferedUsageWriter()
        await writer.shutdown()


class TestSingletonFactory:
    """单例工厂函数"""

    def test_get_returns_buffered_usage_writer(self):
        writer = get_buffered_usage_writer()
        assert isinstance(writer, BufferedUsageWriter)

    def test_get_returns_same_instance(self):
        w1 = get_buffered_usage_writer()
        w2 = get_buffered_usage_writer()
        assert w1 is w2


class TestWriteFailure:
    """写入失败时不崩溃"""

    @pytest.mark.asyncio
    async def test_write_failure_does_not_crash(self):
        """DB 异常时 enqueue 不抛异常"""
        repo = MagicMock(spec=UsageRepository)
        repo.batch_record = AsyncMock(side_effect=Exception("DB unavailable"))

        writer = BufferedUsageWriter(usage_repo=repo)

        with patch(
            "app.services.llm.buffered_usage_writer.async_session_factory"
        ) as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_ctx

            # 不应抛异常
            await writer.enqueue(session_id="s1", total_tokens=100)
