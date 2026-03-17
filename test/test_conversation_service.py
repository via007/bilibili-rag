"""
Bilibili RAG 会话服务测试
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.conversation import ConversationService
from app.models import ChatSession, ChatMessage


class TestConversationService:
    """会话服务测试类"""

    async def test_create_session(self, test_db):
        """测试创建会话"""
        service = ConversationService(test_db)

        session = await service.create_session(
            user_session_id="test_user_001",
            title="测试会话",
            folder_ids=[1, 2]
        )

        assert session is not None
        assert session.session_id is not None
        assert session.user_session_id == "test_user_001"
        assert session.title == "测试会话"
        assert session.folder_ids == [1, 2]
        assert session.message_count == 0
        assert session.is_archived is False
        assert session.is_deleted is False

    async def test_create_session_default_title(self, test_db):
        """测试创建会话使用默认标题"""
        service = ConversationService(test_db)

        session = await service.create_session(
            user_session_id="test_user_001"
        )

        assert session.title == "新会话"

    async def test_get_session(self, test_db_with_data):
        """测试获取会话"""
        service = ConversationService(test_db_with_data)

        session = await service.get_session("session_001")

        assert session is not None
        assert session.session_id == "session_001"
        assert session.title == "测试会话1"

    async def test_get_session_not_found(self, test_db_with_data):
        """测试获取不存在的会话"""
        service = ConversationService(test_db_with_data)

        session = await service.get_session("nonexistent_session")

        assert session is None

    async def test_get_session_by_user(self, test_db_with_data):
        """测试根据用户ID获取会话"""
        service = ConversationService(test_db_with_data)

        session = await service.get_session_by_user("session_001", "test_user_001")

        assert session is not None
        assert session.session_id == "session_001"

    async def test_get_session_by_user_wrong_user(self, test_db_with_data):
        """测试用户不匹配时返回None"""
        service = ConversationService(test_db_with_data)

        session = await service.get_session_by_user("session_001", "wrong_user")

        assert session is None

    async def test_list_sessions(self, test_db_with_data, test_user_session_id):
        """测试列出用户会话"""
        service = ConversationService(test_db_with_data)

        sessions, total = await service.list_sessions(
            user_session_id=test_user_session_id,
            page=1,
            page_size=10
        )

        assert total == 2  # 只有2个未归档的会话
        assert len(sessions) == 2

    async def test_list_sessions_with_archived(self, test_db_with_data, test_user_session_id):
        """测试列出包含归档会话"""
        service = ConversationService(test_db_with_data)

        sessions, total = await service.list_sessions(
            user_session_id=test_user_session_id,
            page=1,
            page_size=10,
            include_archived=True
        )

        assert total == 3  # 包含归档会话

    async def test_list_sessions_pagination(self, test_db_with_data, test_user_session_id):
        """测试分页"""
        service = ConversationService(test_db_with_data)

        sessions, total = await service.list_sessions(
            user_session_id=test_user_session_id,
            page=1,
            page_size=1
        )

        assert total == 2
        assert len(sessions) == 1
        assert sessions[0].title == "测试会话1"  # 按最后消息时间排序

    async def test_update_session_title(self, test_db_with_data):
        """测试更新会话标题"""
        service = ConversationService(test_db_with_data)

        session = await service.update_session(
            chat_session_id="session_001",
            user_session_id="test_user_001",
            title="新标题"
        )

        assert session is not None
        assert session.title == "新标题"

    async def test_update_session_archived(self, test_db_with_data):
        """测试归档会话"""
        service = ConversationService(test_db_with_data)

        session = await service.update_session(
            chat_session_id="session_001",
            user_session_id="test_user_001",
            is_archived=True
        )

        assert session is not None
        assert session.is_archived is True

    async def test_update_session_not_found(self, test_db_with_data):
        """测试更新不存在的会话"""
        service = ConversationService(test_db_with_data)

        session = await service.update_session(
            chat_session_id="nonexistent",
            user_session_id="test_user_001",
            title="新标题"
        )

        assert session is None

    async def test_delete_session(self, test_db_with_data):
        """测试删除会话（软删除）"""
        from sqlalchemy import select

        service = ConversationService(test_db_with_data)

        success = await service.delete_session("session_001", "test_user_001")

        assert success is True

        # 验证软删除 - 直接从数据库查询
        stmt = select(ChatSession).where(ChatSession.session_id == "session_001")
        result = await test_db_with_data.execute(stmt)
        session = result.scalar_one_or_none()
        assert session is not None
        assert session.is_deleted is True

    async def test_delete_session_not_found(self, test_db_with_data):
        """测试删除不存在的会话"""
        service = ConversationService(test_db_with_data)

        success = await service.delete_session("nonexistent", "test_user_001")

        assert success is False

    async def test_add_message(self, test_db):
        """测试添加消息"""
        service = ConversationService(test_db)

        # 先创建会话
        session = await service.create_session(
            user_session_id="test_user_001",
            title="测试会话"
        )

        # 添加用户消息
        message = await service.add_message(
            chat_session_id=session.session_id,
            role="user",
            content="测试问题",
            sources=None,
            route="vector"
        )

        assert message is not None
        assert message.content == "测试问题"
        assert message.role == "user"

        # 验证会话消息数更新
        updated_session = await service.get_session(session.session_id)
        assert updated_session.message_count == 1
        assert updated_session.last_message_at is not None

    async def test_get_messages(self, test_db_with_data):
        """测试获取消息列表"""
        service = ConversationService(test_db_with_data)

        messages, total = await service.get_messages(
            chat_session_id="session_001",
            page=1,
            page_size=10
        )

        assert total == 2
        assert len(messages) == 2

    async def test_get_messages_empty_session(self, test_db):
        """测试获取空会话的消息"""
        service = ConversationService(test_db)

        session = await service.create_session(
            user_session_id="test_user_001"
        )

        messages, total = await service.get_messages(
            chat_session_id=session.session_id,
            page=1,
            page_size=10
        )

        assert total == 0
        assert len(messages) == 0

    async def test_get_messages_pagination(self, test_db_with_data):
        """测试消息分页"""
        service = ConversationService(test_db_with_data)

        messages, total = await service.get_messages(
            chat_session_id="session_001",
            page=1,
            page_size=1
        )

        assert total == 2
        assert len(messages) == 1

    async def test_search_messages(self, test_db_with_data, test_user_session_id):
        """测试搜索消息"""
        service = ConversationService(test_db_with_data)

        results, total = await service.search_messages(
            user_session_id=test_user_session_id,
            query="Python",
            page=1,
            page_size=10
        )

        assert total == 1
        assert len(results) == 1
        assert "Python" in results[0]["content"]

    async def test_search_messages_no_results(self, test_db_with_data, test_user_session_id):
        """测试搜索无结果"""
        service = ConversationService(test_db_with_data)

        results, total = await service.search_messages(
            user_session_id=test_user_session_id,
            query="不存在的内容",
            page=1,
            page_size=10
        )

        assert total == 0
        assert len(results) == 0

    async def test_search_messages_with_highlight(self, test_db_with_data, test_user_session_id):
        """测试搜索消息高亮"""
        service = ConversationService(test_db_with_data)

        results, total = await service.search_messages(
            user_session_id=test_user_session_id,
            query="Python",
            page=1,
            page_size=10
        )

        assert results[0]["highlight"] is not None
        assert "<em>" in results[0]["highlight"]  # 验证高亮标签

    async def test_create_highlight(self, test_db_with_data):
        """测试高亮文本生成"""
        service = ConversationService(test_db_with_data)

        content = "这是关于Python编程的测试内容，包含Python关键词"
        highlight = service._create_highlight(content, "Python")

        assert "<em>Python</em>" in highlight

    async def test_create_highlight_no_match(self, test_db_with_data):
        """测试无匹配时的高亮"""
        service = ConversationService(test_db_with_data)

        content = "这是一段普通内容"
        highlight = service._create_highlight(content, "不存在")

        assert "..." in highlight or len(highlight) > 0

    async def test_get_context_for_llm(self, test_db_with_data):
        """测试获取LLM上下文"""
        service = ConversationService(test_db_with_data)

        context = await service.get_context_for_llm(
            chat_session_id="session_001",
            max_tokens=1000
        )

        assert len(context) > 0
        # 验证按时间顺序
        assert context[0]["role"] == "user"

    async def test_update_session_last_message(self, test_db):
        """测试更新会话最后消息时间"""
        service = ConversationService(test_db)

        session = await service.create_session(
            user_session_id="test_user_001"
        )

        await service.update_session_last_message(session.session_id)

        updated_session = await service.get_session(session.session_id)
        assert updated_session.last_message_at is not None
