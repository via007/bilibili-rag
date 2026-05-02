# app/test/test_vector_models.py
# 分P向量化模型测试

import pytest
import pytest_asyncio
from datetime import datetime


# ==================== AsyncTask 模型测试 ====================

class TestAsyncTaskModel:
    """AsyncTask ORM 模型测试"""

    @pytest.mark.asyncio
    async def test_async_task_creation(self, test_db):
        """测试 AsyncTask 写入"""
        from app.models import AsyncTask

        task = AsyncTask(
            task_id="test-async-001",
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 123, "page_index": 0},
            status="pending",
            progress=0,
        )
        test_db.add(task)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(AsyncTask).where(AsyncTask.task_id == "test-async-001")
        )
        found = result.scalar_one()
        assert found.task_type == "vec_page"
        assert found.status == "pending"
        assert found.progress == 0
        assert found.target == {"bvid": "BV1xx", "cid": 123, "page_index": 0}

    @pytest.mark.asyncio
    async def test_async_task_steps(self, test_db):
        """测试 steps JSON 字段"""
        from app.models import AsyncTask

        steps = [
            {"name": "asr", "status": "done", "progress": 100},
            {"name": "vec", "status": "processing", "progress": 50},
        ]
        task = AsyncTask(
            task_id="test-steps-001",
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 456, "page_index": 1},
            status="processing",
            progress=50,
            steps=steps,
        )
        test_db.add(task)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(AsyncTask).where(AsyncTask.task_id == "test-steps-001")
        )
        found = result.scalar_one()
        assert len(found.steps) == 2
        assert found.steps[0]["name"] == "asr"
        assert found.steps[1]["name"] == "vec"

    @pytest.mark.asyncio
    async def test_async_task_result_and_error(self, test_db):
        """测试 result 和 error 字段"""
        from app.models import AsyncTask

        task = AsyncTask(
            task_id="test-result-001",
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 789, "page_index": 2},
            status="done",
            progress=100,
            result={"chunk_count": 5},
            error=None,
        )
        test_db.add(task)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(AsyncTask).where(AsyncTask.task_id == "test-result-001")
        )
        found = result.scalar_one()
        assert found.status == "done"
        assert found.result == {"chunk_count": 5}
        # completed_at 由 task_store.update() 自动设置，这里只验证 result 字段

    @pytest.mark.asyncio
    async def test_async_task_unique_task_id(self, test_db):
        """task_id 全局唯一，不能重复"""
        from app.models import AsyncTask
        from sqlalchemy.exc import IntegrityError

        task1 = AsyncTask(
            task_id="test-unique-001",
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 100, "page_index": 0},
        )
        test_db.add(task1)
        await test_db.commit()

        task2 = AsyncTask(
            task_id="test-unique-001",  # same task_id
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 101, "page_index": 1},
        )
        test_db.add(task2)
        with pytest.raises(IntegrityError):
            await test_db.commit()
        await test_db.rollback()

    @pytest.mark.asyncio
    async def test_async_task_defaults(self, test_db):
        """测试默认值"""
        from app.models import AsyncTask

        task = AsyncTask(
            task_id="test-defaults-001",
            task_type="vec_page",
            target={"bvid": "BV1xx", "cid": 200, "page_index": 0},
        )
        test_db.add(task)
        await test_db.commit()

        assert task.status == "pending"
        assert task.progress == 0
        assert task.steps is None
        assert task.result is None
        assert task.error is None


# ==================== VideoPage 向量化字段测试 ====================

class TestVideoPageVectorFields:
    """VideoPage 向量化扩展字段测试"""

    @pytest.mark.asyncio
    async def test_video_page_vector_defaults(self, test_db):
        """测试向量化字段默认值"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1vecDefault",
            cid=300,
            page_index=0,
            page_title="P1. 测试",
        )
        test_db.add(page)
        await test_db.commit()

        assert page.is_vectorized == "pending"
        assert page.vectorized_at is None
        assert page.vector_chunk_count == 0
        assert page.vector_error is None

    @pytest.mark.asyncio
    async def test_video_page_vectorized_done(self, test_db):
        """测试向量化完成状态"""
        from app.models import VideoPage
        from datetime import datetime

        now = datetime.utcnow()
        page = VideoPage(
            bvid="BV1vecDone",
            cid=301,
            page_index=0,
            page_title="P1. 完成",
            content="测试内容" * 20,
            content_source="asr",
            is_processed=True,
            is_vectorized="done",
            vectorized_at=now,
            vector_chunk_count=5,
        )
        test_db.add(page)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(VideoPage).where(VideoPage.bvid == "BV1vecDone")
        )
        found = result.scalar_one()
        assert found.is_vectorized == "done"
        assert found.vector_chunk_count == 5
        assert found.vectorized_at == now

    @pytest.mark.asyncio
    async def test_video_page_vectorized_failed(self, test_db):
        """测试向量化失败状态"""
        from app.models import VideoPage

        page = VideoPage(
            bvid="BV1vecFailed",
            cid=302,
            page_index=0,
            page_title="P1. 失败",
            is_processed=True,
            is_vectorized="failed",
            vector_error="ChromaDB 连接失败",
        )
        test_db.add(page)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(VideoPage).where(VideoPage.bvid == "BV1vecFailed")
        )
        found = result.scalar_one()
        assert found.is_vectorized == "failed"
        assert "ChromaDB" in found.vector_error


# ==================== Pydantic Schema 测试 ====================

class TestVectorPydanticSchemas:
    """分P向量化 Pydantic 模型测试"""

    def test_vector_page_status_response__exists(self):
        """VectorPageStatusResponse exists=true"""
        from app.models import VectorPageStatusResponse
        from datetime import datetime

        now = datetime.utcnow()
        resp = VectorPageStatusResponse(
            exists=True,
            bvid="BV1test123",
            cid=123,
            page_index=0,
            page_title="P1. 测试",
            is_processed=True,
            content_preview="这是内容预览...",
            is_vectorized="done",
            vectorized_at=now,
            vector_chunk_count=5,
            vector_error=None,
            chroma_exists=True,
        )
        assert resp.exists is True
        assert resp.is_vectorized == "done"
        assert resp.vector_chunk_count == 5
        assert resp.chroma_exists is True

    def test_vector_page_status_response__not_exists(self):
        """VectorPageStatusResponse exists=false"""
        from app.models import VectorPageStatusResponse

        resp = VectorPageStatusResponse(
            exists=False,
            is_processed=False,
            is_vectorized="pending",
            vector_chunk_count=0,
            chroma_exists=False,
        )
        assert resp.exists is False
        assert resp.bvid is None

    def test_vector_page_status_response__with_steps(self):
        """VectorPageStatusResponse 含 steps"""
        from app.models import VectorPageStatusResponse

        steps = [
            {"name": "asr", "status": "done", "progress": 100},
            {"name": "vec", "status": "done", "progress": 100},
        ]
        resp = VectorPageStatusResponse(
            exists=True,
            is_processed=True,
            is_vectorized="done",
            vector_chunk_count=3,
            chroma_exists=True,
            steps=steps,
        )
        assert resp.steps is not None
        assert len(resp.steps) == 2

    def test_vector_page_task_status(self):
        """VectorPageTaskStatus"""
        from app.models import VectorPageTaskStatus

        status = VectorPageTaskStatus(
            task_id="task-vec-001",
            status="done",
            progress=100,
            message="完成",
            steps=[
                {"name": "asr", "status": "done", "progress": 100},
                {"name": "vec", "status": "done", "progress": 100},
            ],
            result={"chunk_count": 5},
        )
        assert status.task_id == "task-vec-001"
        assert status.status == "done"
        assert status.result == {"chunk_count": 5}

    def test_vector_page_task_status__failed(self):
        """VectorPageTaskStatus failed"""
        from app.models import VectorPageTaskStatus

        status = VectorPageTaskStatus(
            task_id="task-vec-002",
            status="failed",
            progress=50,
            message="失败: ASR 失败",
            error="ASR 失败: 网络错误",
        )
        assert status.status == "failed"
        assert status.error is not None

    def test_vector_page_create_request(self):
        """VectorPageCreateRequest"""
        from app.models import VectorPageCreateRequest

        req = VectorPageCreateRequest(
            bvid="BV1create123",
            cid=456,
            page_index=0,
            page_title="P1. 新建",
        )
        assert req.bvid == "BV1create123"
        assert req.cid == 456
        assert req.page_index == 0

    def test_vector_page_revector_request(self):
        """VectorPageReVectorRequest"""
        from app.models import VectorPageReVectorRequest

        req = VectorPageReVectorRequest(bvid="BV1revector123", cid=789)
        assert req.bvid == "BV1revector123"
        assert req.cid == 789
