"""
Bilibili RAG 知识库系统
对话会话管理路由
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    ChatSessionListResponse,
    ChatSessionInfo,
    ChatSessionCreateResponse,
    ChatSessionUpdateRequest,
    ChatMessageListResponse,
    ChatMessageInfo,
    ConversationSearchResponse,
    ConversationSearchResult,
)
from app.services.conversation import ConversationService


class ChatSessionCreateRequest(BaseModel):
    """创建会话请求"""
    user_session_id: str
    title: Optional[str] = None
    folder_ids: Optional[list[int]] = None


router = APIRouter(prefix="/conversation", tags=["会话管理"])


def get_conversation_service(db: AsyncSession = Depends(get_db)) -> ConversationService:
    """获取会话服务实例"""
    return ConversationService(db)


@router.get("/list", response_model=ChatSessionListResponse)
async def list_conversations(
    user_session_id: str = Query(..., description="用户登录 session"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    include_archived: bool = Query(False, description="是否包含已归档的会话"),
    service: ConversationService = Depends(get_conversation_service)
):
    """获取会话列表"""
    sessions, total = await service.list_sessions(
        user_session_id=user_session_id,
        page=page,
        page_size=page_size,
        include_archived=include_archived
    )

    session_infos = [
        ChatSessionInfo(
            chat_session_id=s.session_id,
            title=s.title,
            folder_ids=s.folder_ids,
            message_count=s.message_count,
            last_message_at=s.last_message_at,
            created_at=s.created_at,
            is_archived=s.is_archived
        )
        for s in sessions
    ]

    return ChatSessionListResponse(
        sessions=session_infos,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/create", response_model=ChatSessionCreateResponse)
async def create_conversation(
    request: ChatSessionCreateRequest,
    service: ConversationService = Depends(get_conversation_service)
):
    """创建新会话"""
    session = await service.create_session(
        user_session_id=request.user_session_id,
        title=request.title,
        folder_ids=request.folder_ids
    )

    return ChatSessionCreateResponse(
        chat_session_id=session.session_id,
        title=session.title or "新会话",
        created_at=session.created_at
    )


@router.get("/{chat_session_id}", response_model=ChatSessionInfo)
async def get_conversation(
    chat_session_id: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    service: ConversationService = Depends(get_conversation_service)
):
    """获取会话详情"""
    session = await service.get_session_by_user(chat_session_id, user_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return ChatSessionInfo(
        chat_session_id=session.session_id,
        title=session.title,
        folder_ids=session.folder_ids,
        message_count=session.message_count,
        last_message_at=session.last_message_at,
        created_at=session.created_at,
        is_archived=session.is_archived
    )


@router.put("/{chat_session_id}", response_model=ChatSessionInfo)
async def update_conversation(
    chat_session_id: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    request: ChatSessionUpdateRequest = None,
    service: ConversationService = Depends(get_conversation_service)
):
    """更新会话（重命名、归档）"""
    session = await service.update_session(
        chat_session_id=chat_session_id,
        user_session_id=user_session_id,
        title=request.title if request else None,
        is_archived=request.is_archived if request else None
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return ChatSessionInfo(
        chat_session_id=session.session_id,
        title=session.title,
        folder_ids=session.folder_ids,
        message_count=session.message_count,
        last_message_at=session.last_message_at,
        created_at=session.created_at,
        is_archived=session.is_archived
    )


@router.delete("/{chat_session_id}")
async def delete_conversation(
    chat_session_id: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    service: ConversationService = Depends(get_conversation_service)
):
    """删除会话（软删除）"""
    success = await service.delete_session(chat_session_id, user_session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "会话已删除"}


@router.get("/{chat_session_id}/messages", response_model=ChatMessageListResponse)
async def get_conversation_messages(
    chat_session_id: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页数量"),
    service: ConversationService = Depends(get_conversation_service)
):
    """获取会话消息列表"""
    # 验证会话归属
    session = await service.get_session_by_user(chat_session_id, user_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages, total = await service.get_messages(
        chat_session_id=chat_session_id,
        page=page,
        page_size=page_size
    )

    message_infos = [
        ChatMessageInfo(
            id=m.id,
            role=m.role,
            content=m.content,
            sources=m.sources,
            route=m.route,
            created_at=m.created_at
        )
        for m in messages
    ]

    return ChatMessageListResponse(
        messages=message_infos,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/search", response_model=ConversationSearchResponse)
async def search_conversations(
    user_session_id: str = Query(..., description="用户登录 session"),
    query: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: ConversationService = Depends(get_conversation_service)
):
    """搜索对话内容"""
    results, total = await service.search_messages(
        user_session_id=user_session_id,
        query=query,
        page=page,
        page_size=page_size
    )

    search_results = [
        ConversationSearchResult(
            chat_session_id=r["chat_session_id"],
            session_title=r["session_title"],
            message_id=r["message_id"],
            content=r["content"],
            highlight=r["highlight"],
            created_at=r["created_at"]
        )
        for r in results
    ]

    return ConversationSearchResponse(
        results=search_results,
        total=total,
        page=page,
        page_size=page_size
    )
