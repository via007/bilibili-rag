"""
Bilibili RAG 知识库系统
对话会话管理服务
"""
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatSession, ChatMessage
from app.config import settings
from langchain_core.messages import HumanMessage, SystemMessage
from app.services.llm_factory import get_llm_client


class ConversationService:
    """会话管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        user_session_id: str,
        title: Optional[str] = None,
        folder_ids: Optional[List[int]] = None
    ) -> ChatSession:
        """创建新会话"""
        chat_session_id = str(uuid.uuid4())

        # 如果没有提供标题，使用默认标题
        if not title:
            title = "新会话"

        session = ChatSession(
            session_id=chat_session_id,
            user_session_id=user_session_id,
            title=title,
            folder_ids=folder_ids,
            message_count=0,
            last_message_at=None,
            is_archived=False,
            is_deleted=False
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, chat_session_id: str) -> Optional[ChatSession]:
        """获取会话"""
        stmt = select(ChatSession).where(
            ChatSession.session_id == chat_session_id,
            ChatSession.is_deleted == False
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_by_user(
        self,
        chat_session_id: str,
        user_session_id: str
    ) -> Optional[ChatSession]:
        """根据会话ID和用户ID获取会话"""
        stmt = select(ChatSession).where(
            ChatSession.session_id == chat_session_id,
            ChatSession.user_session_id == user_session_id,
            ChatSession.is_deleted == False
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_session_id: str,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False
    ) -> Tuple[List[ChatSession], int]:
        """获取会话列表"""
        # 构建查询条件
        conditions = [
            ChatSession.user_session_id == user_session_id,
            ChatSession.is_deleted == False
        ]
        if not include_archived:
            conditions.append(ChatSession.is_archived == False)

        # 查询总数
        count_stmt = select(func.count()).select_from(ChatSession).where(*conditions)
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询列表
        offset = (page - 1) * page_size
        stmt = (
            select(ChatSession)
            .where(*conditions)
            .order_by(desc(ChatSession.last_message_at), desc(ChatSession.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        sessions = result.scalars().all()

        return list(sessions), total

    async def update_session(
        self,
        chat_session_id: str,
        user_session_id: str,
        title: Optional[str] = None,
        is_archived: Optional[bool] = None
    ) -> Optional[ChatSession]:
        """更新会话"""
        session = await self.get_session_by_user(chat_session_id, user_session_id)
        if not session:
            return None

        if title is not None:
            session.title = title
        if is_archived is not None:
            session.is_archived = is_archived

        session.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def delete_session(self, chat_session_id: str, user_session_id: str) -> bool:
        """删除会话（软删除）"""
        session = await self.get_session_by_user(chat_session_id, user_session_id)
        if not session:
            return False

        session.is_deleted = True
        session.updated_at = datetime.utcnow()
        await self.db.commit()
        return True

    async def add_message(
        self,
        chat_session_id: str,
        role: str,
        content: str,
        sources: Optional[List[dict]] = None,
        route: Optional[str] = None,
        context_token_count: int = 0
    ) -> ChatMessage:
        """添加消息"""
        message = ChatMessage(
            chat_session_id=chat_session_id,
            role=role,
            content=content,
            sources=sources,
            route=route,
            context_token_count=context_token_count
        )
        self.db.add(message)

        # 更新会话的 message_count 和 last_message_at
        session = await self.get_session(chat_session_id)
        if session:
            session.message_count += 1
            session.last_message_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(
        self,
        chat_session_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[ChatMessage], int]:
        """获取消息列表"""
        # 查询总数
        count_stmt = select(func.count()).select_from(ChatMessage).where(
            ChatMessage.chat_session_id == chat_session_id
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询列表
        offset = (page - 1) * page_size
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == chat_session_id)
            .order_by(ChatMessage.created_at)
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        return list(messages), total

    async def get_context_for_llm(
        self,
        chat_session_id: str,
        max_tokens: int = 4000
    ) -> List[dict]:
        """获取用于 LLM 的上下文消息"""
        messages, _ = await self.get_messages(chat_session_id, page=1, page_size=100)

        context = []
        token_count = 0

        # 从最新消息往前添加
        for msg in reversed(messages):
            msg_tokens = len(msg.content) // 4  # 粗略估算
            if token_count + msg_tokens > max_tokens:
                break
            context.insert(0, {
                "role": msg.role,
                "content": msg.content
            })
            token_count += msg_tokens

        return context

    async def generate_session_title(self, first_question: str) -> str:
        """使用 LLM 生成会话标题"""
        try:
            client = get_llm_client()
            response = client.invoke([
                SystemMessage(content="你是一个标题生成器。请根据用户的问题生成一个简短（最多20字）的会话标题。只输出标题，不要任何解释。"),
                HumanMessage(content=first_question)
            ])
            title = response.content or ""
            return title.strip()[:20]
        except Exception as e:
            # 如果生成失败，使用默认标题
            return "新会话"

    async def update_session_last_message(self, chat_session_id: str) -> None:
        """更新会话的最后消息时间"""
        session = await self.get_session(chat_session_id)
        if session:
            session.last_message_at = datetime.utcnow()
            await self.db.commit()

    async def search_messages(
        self,
        user_session_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[dict], int]:
        """搜索对话内容"""
        # 先找到用户的所有会话
        session_stmt = select(ChatSession.session_id).where(
            ChatSession.user_session_id == user_session_id,
            ChatSession.is_deleted == False
        )
        session_result = await self.db.execute(session_stmt)
        session_ids = [row[0] for row in session_result.fetchall()]

        if not session_ids:
            return [], 0

        # 在这些会话的消息中搜索
        search_pattern = f"%{query}%"

        # 查询总数
        count_stmt = select(func.count()).select_from(ChatMessage).where(
            ChatMessage.chat_session_id.in_(session_ids),
            ChatMessage.content.ilike(search_pattern)
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询列表
        offset = (page - 1) * page_size
        stmt = (
            select(ChatMessage, ChatSession.title)
            .join(ChatSession, ChatSession.session_id == ChatMessage.chat_session_id)
            .where(
                ChatMessage.chat_session_id.in_(session_ids),
                ChatMessage.content.ilike(search_pattern)
            )
            .order_by(desc(ChatMessage.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        rows = result.fetchall()

        results = []
        for msg, session_title in rows:
            # 生成高亮文本
            highlight = self._create_highlight(msg.content, query)
            results.append({
                "chat_session_id": msg.chat_session_id,
                "session_title": session_title,
                "message_id": msg.id,
                "content": msg.content,
                "highlight": highlight,
                "created_at": msg.created_at
            })

        return results, total

    def _create_highlight(self, content: str, query: str, context_chars: int = 50) -> str:
        """创建高亮文本"""
        import re

        # 找到查询词第一次出现的位置
        match = re.search(re.escape(query), content, re.IGNORECASE)
        if not match:
            # 如果没有找到匹配，返回内容前200字符
            return content[:200] + "..." if len(content) > 200 else content

        start = max(0, match.start() - context_chars)
        end = min(len(content), match.end() + context_chars)

        # 提取上下文片段
        snippet = content[start:end]

        # 添加省略号
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        # 高亮关键词
        snippet = re.sub(
            f"({re.escape(query)})",
            r"<em>\1</em>",
            snippet,
            flags=re.IGNORECASE
        )

        return snippet
