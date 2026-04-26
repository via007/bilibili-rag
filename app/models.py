"""
Bilibili RAG 知识库系统

数据模型定义
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from enum import Enum

Base = declarative_base()


# ==================== SQLAlchemy 模型 ====================

class VideoCache(Base):
    """视频内容缓存表"""
    __tablename__ = 'video_cache'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), unique=True, index=True, nullable=False)
    cid = Column(Integer, nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    owner_name = Column(String(100), nullable=True)  # UP主名称
    owner_mid = Column(Integer, nullable=True)  # UP主ID
    
    # 内容
    content = Column(Text, nullable=True)  # 摘要/字幕文本
    content_source = Column(String(20), nullable=True)  # ai_summary / subtitle / basic_info
    outline_json = Column(JSON, nullable=True)  # 分段提纲
    
    # 元信息
    duration = Column(Integer, nullable=True)  # 视频时长（秒）
    pic_url = Column(String(500), nullable=True)  # 封面URL
    
    # 处理状态
    is_processed = Column(Boolean, default=False)  # 是否已处理并加入向量库
    process_error = Column(Text, nullable=True)  # 处理错误信息
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSession(Base):
    """用户会话表"""
    __tablename__ = 'user_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    
    # B站用户信息
    bili_mid = Column(Integer, nullable=True)  # B站用户ID
    bili_uname = Column(String(100), nullable=True)  # B站用户名
    bili_face = Column(String(500), nullable=True)  # 头像URL
    
    # Cookie 信息（加密存储更安全，这里简化处理）
    sessdata = Column(Text, nullable=True)
    bili_jct = Column(Text, nullable=True)
    dedeuserid = Column(String(50), nullable=True)
    
    # 状态
    is_valid = Column(Boolean, default=True)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class FavoriteFolder(Base):
    """收藏夹记录表"""
    __tablename__ = 'favorite_folders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    
    # B站收藏夹信息  
    media_id = Column(Integer, nullable=False)  # 收藏夹ID
    fid = Column(Integer, nullable=True)  # 原始ID
    title = Column(String(200), nullable=False)
    media_count = Column(Integer, default=0)  # 视频数量
    
    # 状态
    is_selected = Column(Boolean, default=True)  # 是否选中用于知识库
    last_sync_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FavoriteVideo(Base):
    """收藏夹-视频关联表"""
    __tablename__ = 'favorite_videos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, index=True, nullable=False)  # 关联 FavoriteFolder.id
    bvid = Column(String(20), index=True, nullable=False)
    
    # 是否选中（用户可以取消选中某些视频）
    is_selected = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== Pydantic 模型 (API 用) ====================

class ContentSource(str, Enum):
    """内容来源"""
    AI_SUMMARY = "ai_summary"
    SUBTITLE = "subtitle"
    BASIC_INFO = "basic_info"
    ASR = "asr"


class VideoInfo(BaseModel):
    """视频信息"""
    bvid: str
    cid: Optional[int] = None
    title: str
    description: Optional[str] = None
    owner_name: Optional[str] = None
    owner_mid: Optional[int] = None
    duration: Optional[int] = None
    pic_url: Optional[str] = None


class VideoContent(BaseModel):
    """视频内容（含摘要）"""
    bvid: str
    title: str
    content: str
    source: ContentSource
    outline: Optional[list] = None


class QRCodeResponse(BaseModel):
    """二维码响应"""
    qrcode_key: str
    qrcode_url: str
    qrcode_image_base64: str


class LoginStatusResponse(BaseModel):
    """登录状态响应"""
    status: str  # waiting / scanned / confirmed / expired
    message: str
    user_info: Optional[dict] = None
    session_id: Optional[str] = None


class FavoriteFolderInfo(BaseModel):
    """收藏夹信息"""
    media_id: int
    title: str
    media_count: int
    is_selected: bool = True
    is_default: Optional[bool] = None


class WorkspacePage(BaseModel):
    """工作区页面（用户选中的已向量化分P）"""
    bvid: str
    cid: int
    page_index: int = 0
    page_title: Optional[str] = None


class ChatRequest(BaseModel):
    """对话请求"""
    question: str
    session_id: Optional[str] = None
    folder_ids: Optional[list[int]] = None  # 指定收藏夹，None 表示全部
    workspace_pages: Optional[list[WorkspacePage]] = None  # 工作区选中的分P


class ChatResponse(BaseModel):
    """对话响应"""
    answer: str
    sources: list[dict]  # 来源视频列表


class ReasoningStepResponse(BaseModel):
    """Agentic RAG 推理步骤"""
    step: int
    action: str
    query: str = ""
    reasoning: str = ""
    verdict: Optional[str] = None
    recall_score: Optional[float] = None
    sources: list[dict] = []
    content_preview: str = ""


class AgenticChatResponse(BaseModel):
    """Agentic RAG 对话响应"""
    answer: str
    sources: list[dict]
    reasoning_steps: list[ReasoningStepResponse]
    synthesis_method: str
    hops_used: int
    avg_recall_score: float = 0.0


class VideoPageInfo(BaseModel):
    """单个分P信息"""
    cid: int
    page: int  # 1-based
    title: str  # B站 part 字段
    duration: int


class VideoPagesResponse(BaseModel):
    """GET /api/knowledge/video/{bvid}/pages 响应"""
    bvid: str
    title: str
    pages: list[VideoPageInfo]
    page_count: int


# ==================== VideoPage & VideoPageVersion (分P ASR) ====================

class VideoPage(Base):
    """视频分P信息表"""
    __tablename__ = 'video_pages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), index=True, nullable=False)
    cid = Column(Integer, nullable=False)  # B站唯一标识
    page_index = Column(Integer, nullable=False)  # 0-based P序号
    page_title = Column(String(500), nullable=True)  # 如 "P1. 引言"

    # ASR 内容（当前最新版本）
    content = Column(Text, nullable=True)  # ASR 转写文字
    content_source = Column(String(20), nullable=True)  # asr / user_edit
    is_processed = Column(Boolean, default=False)  # ASR 是否完成
    version = Column(Integer, default=1)  # 当前版本号

    # 向量化状态（v2 新增）
    is_vectorized = Column(String(20), default="pending")  # pending / processing / done / failed
    vectorized_at = Column(DateTime, nullable=True)
    vector_chunk_count = Column(Integer, default=0)
    vector_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bvid', 'cid', name='uq_video_page_bvid_cid'),
        UniqueConstraint('bvid', 'page_index', name='uq_video_page_bvid_index'),
    )


class VideoPageVersion(Base):
    """分P ASR 版本历史表"""
    __tablename__ = 'video_page_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), index=True, nullable=False)
    cid = Column(Integer, nullable=False)
    page_index = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)

    content = Column(Text, nullable=True)
    content_source = Column(String(20), nullable=True)  # asr / user_edit
    is_latest = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bvid', 'cid', 'version', name='uq_video_page_version'),
    )


class AsyncTask(Base):
    """通用异步任务表"""
    __tablename__ = 'async_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, index=True, nullable=False)
    task_type = Column(String(20), nullable=False)  # vec_page / asr / ...
    target = Column(JSON, nullable=False)  # {"bvid": "BV1xx", "cid": 123, "page_index": 0}
    status = Column(String(20), default="pending")  # pending / processing / done / failed
    progress = Column(Integer, default=0)
    steps = Column(JSON, nullable=True)  # [{"name": "asr", "status": "done", "progress": 100}, ...]
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# ==================== Pydantic 模型 (ASR 分P) ====================

class ASRCreateRequest(BaseModel):
    """POST /asr/create 请求"""
    bvid: str
    cid: int
    page_index: int = 0
    page_title: Optional[str] = None


class ASRUpdateRequest(BaseModel):
    """POST /asr/update 请求"""
    bvid: str
    cid: int
    page_index: int
    content: str


class ASRReASRRequest(BaseModel):
    """POST /asr/reasr 请求"""
    bvid: str
    cid: int
    page_index: int


class ASRContentResponse(BaseModel):
    """GET /asr/content 响应"""
    exists: bool
    bvid: Optional[str] = None
    cid: Optional[int] = None
    page_index: Optional[int] = None
    page_title: Optional[str] = None
    content: Optional[str] = None
    content_source: Optional[str] = None
    version: Optional[int] = None
    is_processed: Optional[bool] = None


class ASRTaskStatus(BaseModel):
    """ASR 任务状态"""
    task_id: str
    status: str  # pending / processing / done / failed
    progress: int
    message: str


class VideoPageVersionInfo(BaseModel):
    """版本历史信息"""
    version: int
    content_source: str
    content_preview: str
    is_latest: bool
    created_at: datetime


# ==================== Pydantic 模型 (分P向量化) ====================

class VectorPageStatusResponse(BaseModel):
    """GET /vec/page/status 响应"""
    exists: bool
    bvid: Optional[str] = None
    cid: Optional[int] = None
    page_index: Optional[int] = None
    page_title: Optional[str] = None
    is_processed: bool
    content_preview: Optional[str] = None
    is_vectorized: str  # pending / processing / done / failed
    vectorized_at: Optional[datetime] = None
    vector_chunk_count: int = 0
    vector_error: Optional[str] = None
    chroma_exists: bool
    steps: Optional[list[dict]] = None  # 子步骤透传


class VectorPageTaskStatus(BaseModel):
    """GET /vec/page/status/{task_id} 响应"""
    task_id: str
    status: str  # pending / processing / done / failed
    progress: int
    message: str
    steps: Optional[list[dict]] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class VectorPageCreateRequest(BaseModel):
    """POST /vec/page/create 请求"""
    bvid: str
    cid: int
    page_index: int = 0
    page_title: Optional[str] = None


class VectorPageReVectorRequest(BaseModel):
    """POST /vec/page/revector 请求"""
    bvid: str
    cid: int
