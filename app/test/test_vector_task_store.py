# app/test/test_vector_task_store.py
# TaskStore 持久化层测试
#
# 注意：app/services/__init__.py 导入 RAGService 时依赖 langchain.text_splitter（项目已有环境问题）。
# 此文件通过 conftest.py 的 pytest_collection_modifyitems 机制来跳过，避免模块加载时导入失败。

import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base, AsyncTask


# ==================== SQLiteTaskPersistence 测试 ====================

@pytest_asyncio.fixture(scope="function")
async def store():
    """创建独立的 task_store 测试环境（使用 importlib 绕过 services.__init__）"""
    # 使用 importlib 直接加载模块，避免触发 app.services.__init__.py
    import importlib.util

    # 直接加载 task_store（不通过 package import）
    spec = importlib.util.spec_from_file_location(
        "task_store_module",
        "app/services/task_store.py"
    )
    task_store_module = importlib.util.module_from_spec(spec)

    # 先注入 get_db_context mock
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # patch get_db_context
    import app.database
    original = app.database.get_db_context

    @asynccontextmanager
    async def mock_context():
        async with async_session_factory() as session:
            yield session

    app.database.get_db_context = mock_context

    # 注入 database 模块引用到 task_store
    import app.database as db_module
    import app.models as models_module
    task_store_module.__dict__["get_db_context"] = mock_context
    task_store_module.__dict__["AsyncTask"] = AsyncTask
    task_store_module.__dict__["db_module"] = db_module
    task_store_module.__dict__["models_module"] = models_module
    task_store_module.__dict__["select"] = __import__("sqlalchemy").select

    # 现在加载模块
    spec.loader.exec_module(task_store_module)

    SQLiteTaskPersistence = task_store_module.SQLiteTaskPersistence
    store_instance = SQLiteTaskPersistence()

    yield store_instance

    # 恢复
    app.database.get_db_context = original
    await engine.dispose()


class TestSQLiteTaskPersistence:

    @pytest.mark.asyncio
    async def test_create_task(self, store):
        """创建任务"""
        await store.create(
            task_id="store-001",
            task_type="vec_page",
            target={"bvid": "BV1create", "cid": 100, "page_index": 0},
        )

        task = await store.get("store-001")
        assert task is not None
        assert task["task_id"] == "store-001"
        assert task["task_type"] == "vec_page"
        assert task["status"] == "pending"
        assert task["progress"] == 0

    @pytest.mark.asyncio
    async def test_update_task(self, store):
        """更新任务"""
        await store.create(
            task_id="store-002",
            task_type="vec_page",
            target={"bvid": "BV1update", "cid": 200, "page_index": 1},
        )

        await store.update(
            "store-002",
            status="processing",
            progress=50,
            steps=[{"name": "vec", "status": "processing", "progress": 50}],
        )

        task = await store.get("store-002")
        assert task["status"] == "processing"
        assert task["progress"] == 50
        assert task["steps"][0]["name"] == "vec"

    @pytest.mark.asyncio
    async def test_update_to_done_sets_completed_at(self, store):
        """更新为 done 时自动设置 completed_at"""
        await store.create(
            task_id="store-003",
            task_type="vec_page",
            target={"bvid": "BV1done", "cid": 300, "page_index": 2},
        )

        await store.update(
            "store-003",
            status="done",
            progress=100,
            result={"chunk_count": 5},
        )

        task = await store.get("store-003")
        assert task["status"] == "done"
        assert task["result"] == {"chunk_count": 5}
        assert task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        """获取不存在的任务返回 None"""
        task = await store.get("nonexistent-id")
        assert task is None

    @pytest.mark.asyncio
    async def test_list_pending(self, store):
        """扫描 pending/processing 任务"""
        for i in range(5):
            await store.create(
                task_id=f"store-pending-{i}",
                task_type="vec_page",
                target={"bvid": f"BV1pending{i}", "cid": 400 + i, "page_index": i},
            )

        # 部分更新为 done
        await store.update("store-pending-0", status="done", progress=100)
        await store.update("store-pending-1", status="done", progress=100)

        # 剩下 3 个是 pending
        pending = await store.list_pending("vec_page")
        assert len(pending) == 3
        pending_ids = [t["task_id"] for t in pending]
        assert "store-pending-2" in pending_ids
        assert "store-pending-3" in pending_ids
        assert "store-pending-4" in pending_ids
        assert "store-pending-0" not in pending_ids

    @pytest.mark.asyncio
    async def test_list_pending_empty(self, store):
        """无 pending 任务时返回空列表"""
        pending = await store.list_pending("vec_page")
        assert pending == []

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, store):
        """更新不存在的任务不报错"""
        await store.update("nonexistent-id", status="done")

    @pytest.mark.asyncio
    async def test_task_type_filter(self, store):
        """按 task_type 过滤"""
        await store.create(
            task_id="store-type-vec",
            task_type="vec_page",
            target={"bvid": "BV1vec", "cid": 500, "page_index": 0},
        )
        await store.create(
            task_id="store-type-asr",
            task_type="asr",
            target={"bvid": "BV1asr", "cid": 501, "page_index": 0},
        )

        pending_vec = await store.list_pending("vec_page")
        pending_asr = await store.list_pending("asr")

        assert len(pending_vec) == 1
        assert pending_vec[0]["task_type"] == "vec_page"
        assert len(pending_asr) == 1
        assert pending_asr[0]["task_type"] == "asr"
