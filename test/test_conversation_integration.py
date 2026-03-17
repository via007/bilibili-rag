"""
Bilibili RAG 会话管理集成测试
测试完整的工作流程
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.services.conversation import ConversationService
from app.models import ChatSession, ChatMessage


class TestConversationIntegration:
    """会话管理集成测试类"""

    async def test_full_conversation_workflow(self, test_db):
        """
        测试完整的会话工作流程：
        1. 创建会话
        2. 添加用户消息
        3. 添加助手消息
        4. 获取会话列表
        5. 获取会话详情
        6. 获取消息列表
        7. 更新会话标题
        8. 删除会话
        """
        service = ConversationService(test_db)
        user_session_id = "integration_test_user"

        # 1. 创建会话
        session = await service.create_session(
            user_session_id=user_session_id,
            title="集成测试会话"
        )
        assert session is not None
        session_id = session.session_id

        # 2. 添加用户消息
        user_message = await service.add_message(
            chat_session_id=session_id,
            role="user",
            content="你好，我想了解Python异步编程",
            route="vector"
        )
        assert user_message is not None

        # 3. 添加助手消息
        assistant_message = await service.add_message(
            chat_session_id=session_id,
            role="assistant",
            content="Python异步编程主要使用asyncio模块...",
            sources=[{"bvid": "BV123", "title": "Python教程"}],
            route="vector"
        )
        assert assistant_message is not None

        # 4. 获取会话列表
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10
        )
        assert total == 1
        assert len(sessions) == 1

        # 5. 获取会话详情
        session_detail = await service.get_session_by_user(session_id, user_session_id)
        assert session_detail is not None
        assert session_detail.message_count == 2

        # 6. 获取消息列表
        messages, msg_total = await service.get_messages(
            chat_session_id=session_id,
            page=1,
            page_size=10
        )
        assert msg_total == 2
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

        # 7. 更新会话标题
        updated_session = await service.update_session(
            chat_session_id=session_id,
            user_session_id=user_session_id,
            title="Python异步编程讨论"
        )
        assert updated_session.title == "Python异步编程讨论"

        # 8. 删除会话
        success = await service.delete_session(session_id, user_session_id)
        assert success is True

        # 验证删除后不再显示在列表中
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10
        )
        assert total == 0

    async def test_multi_session_management(self, test_db):
        """测试多会话管理"""
        service = ConversationService(test_db)
        user_session_id = "multi_session_user"

        # 创建多个会话
        session1 = await service.create_session(user_session_id, "会话1")
        session2 = await service.create_session(user_session_id, "会话2")
        session3 = await service.create_session(user_session_id, "会话3")

        # 列出所有会话
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10
        )
        assert total == 3

        # 归档一个会话
        await service.update_session(
            chat_session_id=session2.session_id,
            user_session_id=user_session_id,
            is_archived=True
        )

        # 不包含归档
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10,
            include_archived=False
        )
        assert total == 2

        # 包含归档
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10,
            include_archived=True
        )
        assert total == 3

    async def test_message_search_workflow(self, test_db):
        """测试消息搜索工作流程"""
        service = ConversationService(test_db)
        user_session_id = "search_user"

        # 创建会话并添加消息
        session = await service.create_session(user_session_id, "搜索测试")

        await service.add_message(
            chat_session_id=session.session_id,
            role="user",
            content="如何学习Python的异步编程？",
            route="vector"
        )
        await service.add_message(
            chat_session_id=session.session_id,
            role="assistant",
            content="可以使用asyncio模块...",
            sources=[],
            route="vector"
        )
        await service.add_message(
            chat_session_id=session.session_id,
            role="user",
            content="JavaScript的异步和Python一样吗？",
            route="vector"
        )

        # 搜索Python相关内容
        results, total = await service.search_messages(
            user_session_id=user_session_id,
            query="Python",
            page=1,
            page_size=10
        )
        assert total == 2
        assert any("Python" in r["content"] for r in results)

        # 搜索JavaScript
        results, total = await service.search_messages(
            user_session_id=user_session_id,
            query="JavaScript",
            page=1,
            page_size=10
        )
        assert total == 1

        # 搜索不存在的关键词
        results, total = await service.search_messages(
            user_session_id=user_session_id,
            query="golang",
            page=1,
            page_size=10
        )
        assert total == 0

    async def test_message_pagination_workflow(self, test_db):
        """测试消息分页工作流程"""
        service = ConversationService(test_db)
        user_session_id = "pagination_user"

        session = await service.create_session(user_session_id, "分页测试")

        # 添加10条消息
        for i in range(10):
            await service.add_message(
                chat_session_id=session.session_id,
                role="user",
                content=f"消息 {i+1}",
                route="vector"
            )

        # 测试分页
        page1, total1 = await service.get_messages(session.session_id, page=1, page_size=3)
        assert len(page1) == 3
        assert total1 == 10

        page2, total2 = await service.get_messages(session.session_id, page=2, page_size=3)
        assert len(page2) == 3
        assert total2 == 10

        page4, total4 = await service.get_messages(session.session_id, page=4, page_size=3)
        assert len(page4) == 1  # 最后1条

    async def test_session_isolation_between_users(self, test_db):
        """测试用户之间的会话隔离"""
        service = ConversationService(test_db)

        # 用户A创建会话
        session_a = await service.create_session("user_a", "用户A的会话")

        # 用户B创建会话
        session_b = await service.create_session("user_b", "用户B的会话")

        # 用户A只能看到自己的会话
        sessions_a, total_a = await service.list_sessions("user_a", page=1, page_size=10)
        assert total_a == 1
        assert sessions_a[0].title == "用户A的会话"

        # 用户B只能看到自己的会话
        sessions_b, total_b = await service.list_sessions("user_b", page=1, page_size=10)
        assert total_b == 1
        assert sessions_b[0].title == "用户B的会话"

        # 用户A无法访问用户B的会话
        session_access = await service.get_session_by_user(session_b.session_id, "user_a")
        assert session_access is None

    async def test_archived_session_not_visible_in_list(self, test_db):
        """测试归档会话不在普通列表中显示"""
        service = ConversationService(test_db)
        user_session_id = "archive_user"

        # 创建会话
        session1 = await service.create_session(user_session_id, "正常会话")
        session2 = await service.create_session(user_session_id, "将被归档的会话")

        # 归档一个会话
        await service.update_session(
            chat_session_id=session2.session_id,
            user_session_id=user_session_id,
            is_archived=True
        )

        # 默认不显示归档
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10,
            include_archived=False
        )
        assert total == 1
        assert sessions[0].title == "正常会话"

        # 显式包含归档
        sessions, total = await service.list_sessions(
            user_session_id=user_session_id,
            page=1,
            page_size=10,
            include_archived=True
        )
        assert total == 2

    async def test_context_for_llm_workflow(self, test_db):
        """测试获取LLM上下文的工作流程"""
        service = ConversationService(test_db)
        session = await service.create_session("llm_user", "LLM测试")

        # 添加多条消息
        messages_content = [
            "这是一个很长的测试内容" * 100,
            "这是第二段很长的内容" * 100,
            "这是第三段内容" * 50,
            "最后一段内容"
        ]

        for content in messages_content:
            await service.add_message(
                chat_session_id=session.session_id,
                role="user",
                content=content,
                route="vector"
            )

        # 获取上下文
        context = await service.get_context_for_llm(
            chat_session_id=session.session_id,
            max_tokens=500
        )

        # 验证上下文格式
        assert len(context) > 0
        assert all("role" in msg and "content" in msg for msg in context)

        # 验证token限制
        total_tokens = sum(len(msg["content"]) // 4 for msg in context)
        assert total_tokens <= 500

    async def test_update_folder_ids_in_session(self, test_db):
        """测试在会话中更新关联的收藏夹"""
        service = ConversationService(test_db)
        user_session_id = "folder_user"

        # 创建带有folder_ids的会话
        session = await service.create_session(
            user_session_id=user_session_id,
            title="收藏夹会话",
            folder_ids=[1, 2, 3]
        )

        # 注意: 当前update_session不支持直接更新folder_ids
        # 这里验证folder_ids被正确创建
        retrieved = await service.get_session_by_user(session.session_id, user_session_id)
        assert retrieved.folder_ids == [1, 2, 3]
