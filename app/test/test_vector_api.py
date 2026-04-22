# app/test/test_vector_api.py
# 分P向量化 API 端点测试

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import get_db
from app.models import Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool


# ==================== 测试数据库 Fixture ====================

@pytest_asyncio.fixture(scope="function")
async def test_db():
    """创建内存 SQLite 数据库用于测试"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """创建测试客户端，注入测试数据库"""
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ==================== GET /vec/page/status ====================

class TestGetVecStatus:
    """GET /vec/page/status 测试"""

    @pytest.mark.asyncio
    async def test_status_not_exists(self, client, test_db):
        """VideoPage 不存在返回 exists=false"""
        response = await client.get("/vec/page/status?bvid=BV1notExist&cid=123")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["is_vectorized"] == "pending"
        assert data["chroma_exists"] is False

    @pytest.mark.asyncio
    async def test_status_exists_not_vectorized(self, client, test_db):
        """存在但未向量化"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1noVec",
            cid=111,
            page_index=0,
            page_title="P1. 未向量化",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="pending",
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.vector_page.RAGService") as mock_rag:
            mock_instance = MagicMock()
            mock_instance.get_page_vector_count.return_value = 0
            mock_rag.return_value = mock_instance

            response = await client.get("/vec/page/status?bvid=BV1noVec&cid=111")
            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            assert data["is_vectorized"] == "pending"
            assert data["chroma_exists"] is False

    @pytest.mark.asyncio
    async def test_status_done_chroma_exists(self, client, test_db):
        """已向量化且 ChromaDB 有数据"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1doneVec",
            cid=222,
            page_index=0,
            page_title="P1. 已向量化",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="done",
            vector_chunk_count=5,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.vector_page.RAGService") as mock_rag:
            mock_instance = MagicMock()
            mock_instance.get_page_vector_count.return_value = 5
            mock_rag.return_value = mock_instance

            response = await client.get("/vec/page/status?bvid=BV1doneVec&cid=222")
            assert response.status_code == 200
            data = response.json()
            assert data["is_vectorized"] == "done"
            assert data["chroma_exists"] is True
            assert data["vector_chunk_count"] == 5

    @pytest.mark.asyncio
    async def test_status_consistency_repair__done_but_chroma_empty(self, client, test_db):
        """DB says done 但 ChromaDB 为空 → 自动修复为 failed"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1inconsistent",
            cid=333,
            page_index=0,
            page_title="P1. 不一致",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="done",  # DB 说已完成
            vector_chunk_count=5,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.vector_page.RAGService") as mock_rag:
            mock_instance = MagicMock()
            mock_instance.get_page_vector_count.return_value = 0  # 但 ChromaDB 实际为空
            mock_rag.return_value = mock_instance

            response = await client.get("/vec/page/status?bvid=BV1inconsistent&cid=333")
            assert response.status_code == 200
            data = response.json()
            # 应被修复为 failed
            assert data["is_vectorized"] == "failed"
            assert data["chroma_exists"] is False

    @pytest.mark.asyncio
    async def test_status_consistency_repair__pending_but_chroma_has_data(self, client, test_db):
        """DB says pending 但 ChromaDB 有数据 → 自动修复为 done"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1pendingButData",
            cid=444,
            page_index=0,
            page_title="P1. 后台已完成",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="pending",  # DB 说是 pending
            vector_chunk_count=0,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.vector_page.RAGService") as mock_rag:
            mock_instance = MagicMock()
            mock_instance.get_page_vector_count.return_value = 3  # ChromaDB 实际有 3 个块
            mock_rag.return_value = mock_instance

            response = await client.get("/vec/page/status?bvid=BV1pendingButData&cid=444")
            assert response.status_code == 200
            data = response.json()
            # 应被修复为 done
            assert data["is_vectorized"] == "done"
            assert data["chroma_exists"] is True
            assert data["vector_chunk_count"] == 3


# ==================== POST /vec/page/create ====================

class TestCreateVec:
    """POST /vec/page/create 测试"""

    @pytest.mark.asyncio
    async def test_create_page_not_found(self, client, test_db):
        """VideoPage 不存在返回 404"""
        response = await client.post(
            "/vec/page/create",
            json={"bvid": "BV1notExist", "cid": 123, "page_index": 0},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_already_up_to_date(self, client, test_db):
        """已是最新向量（幂等）"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1upToDate",
            cid=555,
            page_index=0,
            page_title="P1. 最新",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="done",
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        response = await client.post(
            "/vec/page/create",
            json={"bvid": "BV1upToDate", "cid": 555, "page_index": 0},
        )
        assert response.status_code == 200
        data = response.json()
        # 已完成返回 task_id=None
        assert data["task_id"] is None
        assert "已是最新" in data["message"]

    @pytest.mark.asyncio
    async def test_create_pending_triggers_task(self, client, test_db):
        """未向量化触发后台任务"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1pendingTask",
            cid=666,
            page_index=0,
            page_title="P1. 待向量化",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="pending",
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        # Mock create_task 避免真实后台运行，同时 patch task_store 使其用测试数据库
        with patch("app.routers.vector_page.asyncio.create_task") as mock_create_task, \
             patch("app.routers.vector_page._task_store") as mock_store:
            mock_create_task.return_value = MagicMock()
            mock_store.create = AsyncMock(return_value=None)

            response = await client.post(
                "/vec/page/create",
                json={"bvid": "BV1pendingTask", "cid": 666, "page_index": 0},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] is not None
            assert "任务已创建" in data["message"]


# ==================== POST /vec/page/revector ====================

class TestReVector:
    """POST /vec/page/revector 测试"""

    @pytest.mark.asyncio
    async def test_revector_page_not_found(self, client, test_db):
        """VideoPage 不存在返回 404"""
        response = await client.post(
            "/vec/page/revector",
            json={"bvid": "BV1notExist", "cid": 123},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revector_not_processed(self, client, test_db):
        """ASR 未完成不能向量化"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1notProcessed",
            cid=777,
            page_index=0,
            page_title="P1. 未ASR",
            is_processed=False,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        response = await client.post(
            "/vec/page/revector",
            json={"bvid": "BV1notProcessed", "cid": 777},
        )
        assert response.status_code == 400
        assert "ASR 未完成" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_revector_sets_pending(self, client, test_db):
        """强制重建标记 pending"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1rebuild",
            cid=888,
            page_index=0,
            page_title="P1. 重建",
            content="测试内容",
            content_source="asr",
            is_processed=True,
            is_vectorized="done",
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.vector_page.asyncio.create_task") as mock_create_task, \
             patch("app.routers.vector_page._task_store") as mock_store:
            mock_create_task.return_value = MagicMock()
            mock_store.create = AsyncMock(return_value=None)

            response = await client.post(
                "/vec/page/revector",
                json={"bvid": "BV1rebuild", "cid": 888},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] is not None

            # 验证 is_vectorized 已改为 pending
            from sqlalchemy import select
            result = await test_db.execute(
                select(VideoPage).where(VideoPage.bvid == "BV1rebuild")
            )
            updated = result.scalar_one()
            assert updated.is_vectorized == "pending"


# ==================== GET /vec/page/status/{task_id} ====================

class TestGetVecTaskStatus:
    """GET /vec/page/status/{task_id} 测试"""

    @pytest.mark.asyncio
    async def test_status_task_not_found(self, client, test_db):
        """任务不存在返回 404（既不在 task_store 也不在 asr_tasks）"""
        with patch("app.routers.vector_page._task_store") as mock_store:
            mock_store.get = AsyncMock(return_value=None)
            response = await client.get("/vec/page/status/nonexistent-task-id")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_task_in_store(self, client, test_db):
        """任务存在于 task_store"""
        mock_task_data = {
            "task_id": "vec-task-001",
            "status": "done",
            "progress": 100,
            "steps": [{"name": "vec", "status": "done", "progress": 100}],
            "result": {"chunk_count": 5},
            "error": None,
        }
        with patch("app.routers.vector_page._task_store") as mock_store:
            mock_store.get = AsyncMock(return_value=mock_task_data)

            response = await client.get("/vec/page/status/vec-task-001")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "vec-task-001"
            assert data["status"] == "done"
            assert data["result"]["chunk_count"] == 5

    @pytest.mark.asyncio
    async def test_status_task_failed(self, client, test_db):
        """任务失败"""
        mock_task_data = {
            "task_id": "vec-task-002",
            "status": "failed",
            "progress": 40,
            "steps": None,
            "result": None,
            "error": "ASR 失败: 网络错误",
        }
        with patch("app.routers.vector_page._task_store") as mock_store:
            mock_store.get = AsyncMock(return_value=mock_task_data)

            response = await client.get("/vec/page/status/vec-task-002")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "failed"
            assert "ASR" in data["error"]
