"""
Bilibili RAG 会话 API 测试
使用更简单的方式测试 API 路由
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models import ChatSession, ChatMessage


class TestConversationAPIRoutes:
    """测试 API 路由"""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_conversations_validation(self):
        """测试列表会话需要 user_session_id 参数"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/conversation/list")
            # 缺少必需参数会返回 422
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_conversation_validation(self):
        """测试创建会话需要 user_session_id 参数"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/conversation/create", json={})
            # 缺少必需参数会返回 422
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_conversation_requires_params(self):
        """测试获取会话需要参数"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/conversation/session_001")
            # 缺少 user_session_id 参数会返回 422
            assert response.status_code == 422


class TestConversationAPIModels:
    """测试 API 模型"""

    def test_chat_session_create_request_model(self):
        """测试会话创建请求模型"""
        from app.routers.conversation import ChatSessionCreateRequest

        # 正常创建
        req = ChatSessionCreateRequest(user_session_id="test_user")
        assert req.user_session_id == "test_user"
        assert req.title is None

        # 带标题创建
        req = ChatSessionCreateRequest(user_session_id="test_user", title="测试会话")
        assert req.title == "测试会话"

        # 带 folder_ids 创建
        req = ChatSessionCreateRequest(user_session_id="test_user", folder_ids=[1, 2, 3])
        assert req.folder_ids == [1, 2, 3]


class TestConversationResponseModels:
    """测试响应模型"""

    def test_chat_session_info_model(self):
        """测试会话信息模型"""
        from datetime import datetime
        from app.models import ChatSessionInfo

        info = ChatSessionInfo(
            chat_session_id="test_session",
            title="测试会话",
            folder_ids=[1, 2],
            message_count=5,
            last_message_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            is_archived=False
        )

        assert info.chat_session_id == "test_session"
        assert info.message_count == 5

    def test_chat_session_list_response_model(self):
        """测试会话列表响应模型"""
        from datetime import datetime
        from app.models import ChatSessionListResponse, ChatSessionInfo

        sessions = [
            ChatSessionInfo(
                chat_session_id="s1",
                title="会话1",
                folder_ids=None,
                message_count=1,
                last_message_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                is_archived=False
            )
        ]

        response = ChatSessionListResponse(
            sessions=sessions,
            total=1,
            page=1,
            page_size=20
        )

        assert response.total == 1
        assert len(response.sessions) == 1

    def test_chat_message_info_model(self):
        """测试消息信息模型"""
        from datetime import datetime
        from app.models import ChatMessageInfo

        info = ChatMessageInfo(
            id=1,
            role="user",
            content="测试消息",
            sources=[{"bvid": "BV123", "title": "测试"}],
            route="vector",
            created_at=datetime.utcnow()
        )

        assert info.role == "user"
        assert info.content == "测试消息"
