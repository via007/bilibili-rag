"""
test_usage_repository.py — 测试 UsageRepository 的 batch_record 和 record 方法
"""
import pytest
import pytest_asyncio
from sqlalchemy import select, func
from app.repository.usage_repository import UsageRepository, get_usage_repository
from app.models import CredentialUsage


class TestBatchRecord:
    """batch_record() 批量写入测试"""

    @pytest_asyncio.fixture(scope="function")
    async def repo(self):
        return UsageRepository()

    @pytest.mark.asyncio
    async def test_empty_list_noop(self, test_db, repo):
        """空列表不执行任何操作，不抛异常"""
        await repo.batch_record([], test_db)
        # 验证未写入任何记录
        result = await test_db.execute(select(func.count(CredentialUsage.id)))
        count = result.scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_single_record(self, test_db, repo):
        """单条记录正确写入数据库"""
        records = [{
            "session_id": "session-1",
            "credential_id": 1,
            "provider": "openai",
            "model": "gpt-4",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "api_calls": 1,
        }]
        await repo.batch_record(records, test_db)

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "session-1"
        assert row.credential_id == 1
        assert row.provider == "openai"
        assert row.model == "gpt-4"
        assert row.prompt_tokens == 100
        assert row.completion_tokens == 50
        assert row.total_tokens == 150
        assert row.api_calls == 1

    @pytest.mark.asyncio
    async def test_multiple_records(self, test_db, repo):
        """多条记录批量写入，验证数量和内容"""
        records = [
            {
                "session_id": "session-1",
                "provider": "openai",
                "model": "gpt-4",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "api_calls": 1,
            },
            {
                "session_id": "session-1",
                "provider": "anthropic",
                "model": "claude-3",
                "prompt_tokens": 200,
                "completion_tokens": 80,
                "total_tokens": 280,
                "api_calls": 1,
            },
            {
                "session_id": "session-2",
                "provider": "deepseek",
                "model": "deepseek-v3",
                "prompt_tokens": 50,
                "completion_tokens": 30,
                "total_tokens": 80,
                "api_calls": 1,
            },
        ]
        await repo.batch_record(records, test_db)

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 3

        providers = {r.provider for r in rows}
        assert providers == {"openai", "anthropic", "deepseek"}

        total = sum(r.total_tokens for r in rows)
        assert total == 510

    @pytest.mark.asyncio
    async def test_credential_id_null(self, test_db, repo):
        """credential_id 为 None（系统默认 Key）时正确写入"""
        records = [{
            "session_id": "session-1",
            "credential_id": None,
            "provider": "openai",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "api_calls": 1,
        }]
        await repo.batch_record(records, test_db)

        result = await test_db.execute(select(CredentialUsage))
        row = result.scalars().first()
        assert row.credential_id is None
        assert row.total_tokens == 15

    @pytest.mark.asyncio
    async def test_field_integrity_no_default_override(self, test_db, repo):
        """验证 batch_record 不会用 ORM 默认值覆盖传入的显式值"""
        records = [{
            "session_id": "session-x",
            "provider": "custom",
            "model": "custom-model",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 3,
        }]
        await repo.batch_record(records, test_db)

        result = await test_db.execute(select(CredentialUsage))
        row = result.scalars().first()
        assert row.prompt_tokens == 0
        assert row.completion_tokens == 0
        assert row.total_tokens == 0
        assert row.api_calls == 3  # 非默认值 1，确认我们传的值生效了


class TestRecord:
    """record() 单条写入测试"""

    @pytest_asyncio.fixture(scope="function")
    async def repo(self):
        return UsageRepository()

    @pytest.mark.asyncio
    async def test_single_record_commit(self, test_db, repo):
        """record() 方法正确写入并提交"""
        await repo.record(
            session_id="session-abc",
            credential_id=5,
            provider="openai",
            model="gpt-4o",
            prompt_tokens=300,
            completion_tokens=100,
            db=test_db,
        )

        rows = (await test_db.execute(select(CredentialUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "session-abc"
        assert row.credential_id == 5
        assert row.total_tokens == 400


class TestGetUsageRepository:
    """单例工厂函数测试"""

    def test_singleton(self):
        repo1 = get_usage_repository()
        repo2 = get_usage_repository()
        assert repo1 is repo2

    def test_returns_usage_repository(self):
        repo = get_usage_repository()
        assert isinstance(repo, UsageRepository)
