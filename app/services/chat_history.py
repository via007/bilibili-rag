"""
Bilibili RAG 知识库系统

聊天历史服务模块

职责：
- 会话 CRUD（chat_sessions 表）
- 消息状态流管理（chat_messages 表）
- 只操作 chat_sessions / chat_messages 表，不碰其他表

状态流转：
    user 消息: 直接 completed
    assistant 消息: pending → completed / failed
"""
import uuid
import time
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChatSession,
    ChatMessage,
    ChatSessionResponse,
    ChatMessageResponse,
)


# ============================================================================
# 会话管理
# ============================================================================

async def create_chat_session(
    db: AsyncSession,
    session_id: str,
    title: Optional[str] = None,
) -> ChatSessionResponse:
    """创建新会话，生成 chat_session_id（UUID4）"""
    chat_session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    chat_session = ChatSession(
        chat_session_id=chat_session_id,
        session_id=session_id,
        title=title,
        status="active",
        created_at=now,
        updated_at=now,
        last_message_at=None,
    )
    db.add(chat_session)
    await db.commit()
    await db.refresh(chat_session)

    logger.info(f"[CHAT_HISTORY] created session chat_session_id={chat_session_id} session_id={session_id}")
    return ChatSessionResponse.model_validate(chat_session)


async def get_chat_session(
    db: AsyncSession,
    chat_session_id: str,
) -> Optional[ChatSessionResponse]:
    """获取单条会话"""
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_session_id == chat_session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    return ChatSessionResponse.model_validate(session)


async def list_chat_sessions(
    db: AsyncSession,
    session_id: str,
) -> list[ChatSessionResponse]:
    """获取某登录 session 下的所有活跃会话，按 updated_at 降序"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.session_id == session_id)
        .where(ChatSession.status == "active")
        .order_by(desc(ChatSession.updated_at))
    )
    sessions = result.scalars().all()
    return [ChatSessionResponse.model_validate(s) for s in sessions]


async def update_chat_session_title(
    db: AsyncSession,
    chat_session_id: str,
    title: str,
) -> None:
    """更新会话标题（可用于首条消息自动生成标题）"""
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_session_id == chat_session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.warning(f"[CHAT_HISTORY] update_title: session not found chat_session_id={chat_session_id}")
        return

    session.title = title
    session.updated_at = datetime.utcnow()
    await db.commit()
    logger.info(f"[CHAT_HISTORY] updated title chat_session_id={chat_session_id} title={title}")


async def touch_chat_session(
    db: AsyncSession,
    chat_session_id: str,
) -> None:
    """更新 updated_at 和 last_message_at"""
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_session_id == chat_session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.warning(f"[CHAT_HISTORY] touch: session not found chat_session_id={chat_session_id}")
        return

    now = datetime.utcnow()
    session.updated_at = now
    session.last_message_at = now
    await db.commit()


async def delete_chat_session(
    db: AsyncSession,
    chat_session_id: str,
) -> None:
    """删除会话及其所有消息（级联）"""
    # 先删除消息
    await db.execute(
        delete(ChatMessage).where(ChatMessage.chat_session_id == chat_session_id)
    )
    # 再删除会话
    result = await db.execute(
        delete(ChatSession).where(ChatSession.chat_session_id == chat_session_id)
    )
    await db.commit()
    logger.info(f"[CHAT_HISTORY] deleted session chat_session_id={chat_session_id} rows={result.rowcount}")


# ============================================================================
# 消息管理
# ============================================================================

async def save_user_message(
    db: AsyncSession,
    chat_session_id: str,
    content: str,
    sources: Optional[list[dict]] = None,
) -> ChatMessageResponse:
    """保存用户消息，status=completed，返回带 id 的消息"""
    msg = ChatMessage(
        chat_session_id=chat_session_id,
        role="user",
        content=content,
        status="completed",
        sources=sources,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    logger.info(f"[CHAT_HISTORY] saved user_message id={msg.id} chat_session_id={chat_session_id}")
    return ChatMessageResponse.model_validate(msg)


async def create_pending_assistant_message(
    db: AsyncSession,
    chat_session_id: str,
    model: Optional[str] = None,
) -> ChatMessageResponse:
    """创建 assistant 占位消息，status=pending，content=''，返回带 id 的消息"""
    msg = ChatMessage(
        chat_session_id=chat_session_id,
        role="assistant",
        content="",
        status="pending",
        model=model,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    logger.info(f"[CHAT_HISTORY] created pending assistant_message id={msg.id} chat_session_id={chat_session_id}")
    return ChatMessageResponse.model_validate(msg)


async def complete_assistant_message(
    db: AsyncSession,
    message_id: int,
    content: str,
    sources: Optional[list[dict]] = None,
    tokens_used: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> None:
    """SSE 完成后更新 assistant 消息"""
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.id == message_id)
    )
    msg = result.scalar_one_or_none()
    if msg is None:
        logger.warning(f"[CHAT_HISTORY] complete: message not found message_id={message_id}")
        return

    msg.content = content
    msg.status = "completed"
    msg.sources = sources
    msg.tokens_used = tokens_used
    msg.latency_ms = latency_ms
    await db.commit()
    logger.info(f"[CHAT_HISTORY] completed assistant_message id={message_id} len={len(content)}")


async def fail_assistant_message(
    db: AsyncSession,
    message_id: int,
    error: str,
) -> None:
    """SSE 失败后标记 assistant 消息"""
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.id == message_id)
    )
    msg = result.scalar_one_or_none()
    if msg is None:
        logger.warning(f"[CHAT_HISTORY] fail: message not found message_id={message_id}")
        return

    msg.status = "failed"
    msg.error = error
    await db.commit()
    logger.warning(f"[CHAT_HISTORY] failed assistant_message id={message_id} error={error[:100]}")


async def get_history(
    db: AsyncSession,
    chat_session_id: str,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ChatMessageResponse], int]:
    """分页查询历史消息，返回 (messages, total_count)"""
    # 总数
    count_result = await db.execute(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.chat_session_id == chat_session_id)
    )
    total = count_result.scalar() or 0

    # 分页查询，按 created_at 升序（时间线顺序）
    offset = (page - 1) * page_size
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == chat_session_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    messages = result.scalars().all()

    return (
        [ChatMessageResponse.model_validate(m) for m in messages],
        total,
    )


async def clear_history(
    db: AsyncSession,
    chat_session_id: str,
) -> None:
    """清空某会话的所有消息"""
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.chat_session_id == chat_session_id)
    )
    await db.commit()
    logger.info(f"[CHAT_HISTORY] cleared messages chat_session_id={chat_session_id} rows={result.rowcount}")


# ============================================================================
# 便捷函数：获取或创建会话（用于 SSE 接口）
# ============================================================================

async def get_or_create_chat_session(
    db: AsyncSession,
    session_id: str,
    chat_session_id: Optional[str] = None,
    title: Optional[str] = None,
) -> ChatSessionResponse:
    """
    获取或创建聊天会话。

    - 如果 chat_session_id 提供且存在，直接返回
    - 如果 chat_session_id 为空或不存在，创建新会话
    """
    if chat_session_id:
        existing = await get_chat_session(db, chat_session_id)
        if existing:
            return existing
        logger.warning(f"[CHAT_HISTORY] chat_session_id={chat_session_id} not found, creating new")

    return await create_chat_session(db, session_id, title)
