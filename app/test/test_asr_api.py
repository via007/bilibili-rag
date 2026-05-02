# app/test/test_asr_api.py
# ASR API 端点测试

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


# ==================== GET /asr/content ====================

class TestGetASRContent:
    """GET /asr/content 测试"""

    @pytest.mark.asyncio
    async def test_content_not_exists(self, client, test_db):
        """不存在返回 exists=false"""
        response = await client.get("/asr/content?bvid=BV1notExist&cid=123")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False

    @pytest.mark.asyncio
    async def test_content_exists(self, client, test_db):
        """存在返回完整内容"""
        from app.models import VideoPage

        # 写入数据
        page = VideoPage(
            bvid="BV1exist123",
            cid=888,
            page_index=0,
            page_title="P1. 测试",
            content="ASR转写内容",
            content_source="asr",
            is_processed=True,
            version=2,
        )
        test_db.add(page)
        await test_db.commit()

        response = await client.get("/asr/content?bvid=BV1exist123&cid=888")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["bvid"] == "BV1exist123"
        assert data["cid"] == 888
        assert data["content"] == "ASR转写内容"
        assert data["content_source"] == "asr"
        assert data["version"] == 2
        assert data["is_processed"] is True


# ==================== POST /asr/create ====================

class TestCreateASR:
    """POST /asr/create 测试"""

    @pytest.mark.asyncio
    async def test_create_new_task(self, client, test_db):
        """新建 ASR 任务"""
        with patch("app.routers.asr.get_ASRPageService") as mock_get_service:
            mock_service = MagicMock()
            mock_service.process_page = AsyncMock()
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/asr/create",
                json={
                    "bvid": "BV1newTask123",
                    "cid": 111,
                    "page_index": 0,
                    "page_title": "P1. 新建任务",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["task_id"] is not None

    @pytest.mark.asyncio
    async def test_create_idempotent_existing(self, client, test_db):
        """已存在的跳过（幂等）"""
        from app.models import VideoPage

        # 先写入已完成记录
        page = VideoPage(
            bvid="BV1idempotent",
            cid=222,
            page_index=0,
            page_title="P1. 已存在",
            content="已完成的内容",
            content_source="asr",
            is_processed=True,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        response = await client.post(
            "/asr/create",
            json={
                "bvid": "BV1idempotent",
                "cid": 222,
                "page_index": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # 已完成则不创建新任务
        assert data["task_id"] is None
        assert "已完成" in data.get("message", "")


# ==================== POST /asr/update ====================

class TestUpdateASR:
    """POST /asr/update 测试"""

    @pytest.mark.asyncio
    async def test_update_success(self, client, test_db):
        """手动编辑更新成功"""
        from app.models import VideoPage

        # 先写入记录
        page = VideoPage(
            bvid="BV1updateTest",
            cid=333,
            page_index=0,
            page_title="P1. 更新测试",
            content="旧内容",
            content_source="asr",
            is_processed=True,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        response = await client.post(
            "/asr/update",
            json={
                "bvid": "BV1updateTest",
                "cid": 333,
                "content": "用户编辑的新内容",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证更新
        result = await test_db.execute(
            __import__('sqlalchemy').select(VideoPage).where(
                VideoPage.bvid == "BV1updateTest",
                VideoPage.cid == 333
            )
        )
        updated = result.scalar_one()
        assert updated.content == "用户编辑的新内容"
        assert updated.content_source == "user_edit"
        # version 不变（覆盖）
        assert updated.version == 1

    @pytest.mark.asyncio
    async def test_update_not_found(self, client, test_db):
        """记录不存在返回 404"""
        response = await client.post(
            "/asr/update",
            json={
                "bvid": "BV1notExist",
                "cid": 999,
                "content": "新内容",
            },
        )
        assert response.status_code == 404


# ==================== POST /asr/reasr ====================

class TestReASR:
    """POST /asr/reasr 测试"""

    @pytest.mark.asyncio
    async def test_reasr_creates_new_version(self, client, test_db):
        """重新 ASR 新建版本"""
        from app.models import VideoPage, VideoPageVersion

        # 先写入记录
        page = VideoPage(
            bvid="BV1reasrTest",
            cid=444,
            page_index=0,
            page_title="P1. 重新ASR",
            content="v1内容",
            content_source="asr",
            is_processed=True,
            version=1,
        )
        test_db.add(page)
        await test_db.commit()

        with patch("app.routers.asr.get_ASRPageService") as mock_get_service:
            mock_service = MagicMock()
            mock_service.process_page = AsyncMock()
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/asr/reasr",
                json={
                    "bvid": "BV1reasrTest",
                    "cid": 444,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data

            # 验证 version 已更新
            result = await test_db.execute(
                __import__('sqlalchemy').select(VideoPage).where(
                    VideoPage.bvid == "BV1reasrTest",
                    VideoPage.cid == 444
                )
            )
            updated = result.scalar_one()
            assert updated.version == 2
            assert updated.is_processed is False  # 重置为未处理
            assert updated.content is None  # 清空内容

    @pytest.mark.asyncio
    async def test_reasr_not_found(self, client, test_db):
        """记录不存在返回 404"""
        response = await client.post(
            "/asr/reasr",
            json={
                "bvid": "BV1notExist",
                "cid": 999,
            },
        )
        assert response.status_code == 404


# ==================== GET /asr/status/{task_id} ====================

class TestGetASRStatus:
    """GET /asr/status/{task_id} 测试"""

    @pytest.mark.asyncio
    async def test_status_not_found(self, client, test_db):
        """任务不存在返回 404"""
        response = await client.get("/asr/status/nonexistent-task-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_pending(self, client, test_db):
        """pending 状态"""
        from app.routers.asr import asr_tasks

        task_id = "test-task-pending"
        asr_tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
        }

        response = await client.get(f"/asr/status/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["progress"] == 0


# ==================== GET /asr/versions ====================

class TestGetVersions:
    """GET /asr/versions 测试"""

    @pytest.mark.asyncio
    async def test_versions_empty(self, client, test_db):
        """无版本历史"""
        response = await client.get("/asr/versions?bvid=BV1noVersion&cid=123")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_versions_multiple(self, client, test_db):
        """多个版本"""
        from app.models import VideoPageVersion
        from datetime import datetime

        # 写入多个版本
        for v in [1, 2, 3]:
            version = VideoPageVersion(
                bvid="BV1multiVer",
                cid=666,
                page_index=0,
                version=v,
                content=f"v{v}内容",
                content_source="asr",
                is_latest=(v == 3),
                created_at=datetime.utcnow(),
            )
            test_db.add(version)
        await test_db.commit()

        response = await client.get("/asr/versions?bvid=BV1multiVer&cid=666")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # 按 version desc 排序
        assert data[0]["version"] == 3
        assert data[0]["is_latest"] is True
        assert data[1]["is_latest"] is False
