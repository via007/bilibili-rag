"""
Bilibili RAG 知识库系统

数据模型定义
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Index, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional, List
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
    content_source = Column(String(20), nullable=True)  # ai_summary / subtitle / basic_info / asr
    outline_json = Column(JSON, nullable=True)  # 分段提纲

    # 元信息
    duration = Column(Integer, nullable=True)  # 视频时长（秒）
    pic_url = Column(String(500), nullable=True)  # 封面URL

    # 处理状态
    is_processed = Column(Boolean, default=False)  # 是否已处理并加入向量库
    process_error = Column(Text, nullable=True)  # 处理错误信息

    # 向量化进度追踪（新增）
    processing_status = Column(String(20), default="pending")  # pending/processing/completed/failed/no_content
    processing_step = Column(String(50), nullable=True)  # 当前步骤: fetching/asr/embedding/summary
    processing_started_at = Column(DateTime, nullable=True)  # 开始处理时间
    processing_completed_at = Column(DateTime, nullable=True)  # 完成时间

    # ASR 增强字段（新增）
    asr_model = Column(String(50), nullable=True)  # 使用的 ASR 模型
    asr_duration = Column(Integer, nullable=True)  # 音频时长（秒）
    asr_quality_score = Column(Float, nullable=True)  # 质量评分 0-1
    asr_quality_flags = Column(JSON, nullable=True)  # 质量问题标记
    # ["low_confidence", "audio_quality", "too_short", "too_long", "speaker_confusion"]

    is_corrected = Column(Boolean, default=False)  # 是否经过人工校正
    corrected_content = Column(Text, nullable=True)  # 人工校正后的内容
    corrected_at = Column(DateTime, nullable=True)  # 校正时间
    corrected_by = Column(String(50), nullable=True)  # 校正者 (user/moderator)

    # 视频摘要
    summary_json = Column(JSON, nullable=True)  # 结构化摘要

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


class ChatSession(Base):
    """对话会话表"""
    __tablename__ = 'chat_sessions'
    __table_args__ = (
        Index('ix_chat_sessions_user_session_id_is_deleted_is_archived',
              'user_session_id', 'is_deleted', 'is_archived'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)  # 前端会话ID（UUID）
    user_session_id = Column(String(64), nullable=False)  # 关联 UserSession.session_id

    # 会话信息
    title = Column(String(200), nullable=True)  # 会话标题（首问生成或用户自定义）
    folder_ids = Column(JSON, nullable=True)  # 关联的收藏夹ID列表

    # 元信息
    message_count = Column(Integer, default=0)  # 消息数量
    last_message_at = Column(DateTime, nullable=True)  # 最后消息时间

    # 状态
    is_archived = Column(Boolean, default=False)  # 是否归档
    is_deleted = Column(Boolean, default=False)  # 软删除标记

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionSummary(Base):
    """会话总结缓存表"""
    __tablename__ = 'session_summaries'
    __table_args__ = (
        Index('ix_session_summary_chat_session_id', 'chat_session_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(String(64), nullable=False, index=True)

    # 总结内容（Markdown 格式）
    content = Column(Text, nullable=False)

    # 元信息
    version = Column(Integer, default=1)  # 版本号
    source_video_count = Column(Integer)  # 关联视频数
    message_count = Column(Integer)  # 对话轮次
    token_used = Column(Integer)  # 消耗的 token

    # 状态
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    """对话消息表"""
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(String(64), index=True, nullable=False)  # 关联 ChatSession.session_id

    # 消息内容
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)  # 消息内容
    sources = Column(JSON, nullable=True)  # 来源列表 [{"bvid": "", "title": "", "url": ""}]

    # LLM 上下文（用于多轮对话续接）
    context_token_count = Column(Integer, default=0)  # 上下文 token 数量

    # 路由信息（用于调试和分析）
    route = Column(String(20), nullable=True)  # direct / db_list / db_content / vector

    created_at = Column(DateTime, default=datetime.utcnow)


class ASRQualityLog(Base):
    """ASR 质量评分日志"""
    __tablename__ = 'asr_quality_logs'
    __table_args__ = (
        Index('ix_asr_quality_logs_bvid_created_at', 'bvid', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), nullable=False)

    # 质量评估结果
    quality_score = Column(Float, nullable=False)  # 0-1 质量分
    quality_flags = Column(JSON, nullable=True)  # 问题标记列表
    confidence_avg = Column(Float, nullable=True)  # 平均置信度
    confidence_min = Column(Float, nullable=True)  # 最低置信度

    # 音频特征
    audio_duration = Column(Integer, nullable=True)  # 音频时长（秒）
    audio_quality = Column(String(20), nullable=True)  # good/medium/poor
    speech_ratio = Column(Float, nullable=True)  # 语音占比

    # ASR 信息
    asr_model = Column(String(50), nullable=True)  # 使用的模型
    word_count = Column(Integer, nullable=True)  # 字数

    created_at = Column(DateTime, default=datetime.utcnow)


class CorrectionHistory(Base):
    """人工校正历史"""
    __tablename__ = 'correction_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), index=True, nullable=False)

    # 原始内容
    original_content = Column(Text, nullable=False)
    # 校正后内容
    corrected_content = Column(Text, nullable=False)

    # 差异统计
    char_diff = Column(Integer, default=0)  # 字符差异数
    word_diff = Column(Integer, default=0)  # 词差异数

    # 元信息
    correction_type = Column(String(20), default="manual")  # manual/ai_suggest

    created_at = Column(DateTime, default=datetime.utcnow)


class TopicCluster(Base):
    """主题聚类表"""
    __tablename__ = 'topic_clusters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, index=True, nullable=False)
    cluster_index = Column(Integer, nullable=False)
    topic_name = Column(String(200), nullable=True)
    keywords = Column(JSON, nullable=True)  # 关键词列表
    video_count = Column(Integer, default=0)
    difficulty_distribution = Column(JSON, nullable=True)  # 难度分布
    generated_at = Column(DateTime, default=datetime.utcnow)


class ClusterVideo(Base):
    """聚类视频关联表"""
    __tablename__ = 'cluster_videos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, index=True, nullable=False)
    bvid = Column(String(20), index=True, nullable=False)
    order_index = Column(Integer, default=0)


class VideoSummaryDB(Base):
    """视频摘要表（数据库模型）"""
    __tablename__ = 'video_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), unique=True, index=True, nullable=False)
    short_intro = Column(Text, nullable=True)  # 简短介绍
    key_points = Column(JSON, nullable=True)  # 关键要点
    target_audience = Column(String(100), nullable=True)  # 目标受众
    difficulty_level = Column(String(20), nullable=True)  # beginner/intermediate/advanced
    tags = Column(JSON, nullable=True)  # 标签
    is_generated = Column(Boolean, default=False)
    generated_at = Column(DateTime, nullable=True)


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
    # ASR 质量评估字段
    asr_quality_score: Optional[float] = None
    asr_quality_flags: Optional[list] = None
    asr_model: Optional[str] = None
    # 扩展质量评估字段
    confidence_avg: Optional[float] = None
    confidence_min: Optional[float] = None
    audio_duration: Optional[int] = None
    audio_quality: Optional[str] = None
    speech_ratio: Optional[float] = None
    word_count: Optional[int] = None


class VideoSummary(BaseModel):
    """视频结构化摘要"""
    bvid: str
    short_intro: str = ""                    # 一句话简介（50字内）
    key_points: List[str] = []               # 关键要点（3-5个）
    target_audience: str = ""                # 适合人群
    difficulty_level: str = "intermediate"    # 难度级别: beginner/intermediate/advanced
    tags: List[str] = []                     # 标签
    is_generated: bool = False               # 是否已生成
    generated_at: Optional[datetime] = None   # 生成时间


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


class ChatRequest(BaseModel):
    """对话请求"""
    question: str
    session_id: Optional[str] = None
    chat_session_id: Optional[str] = None  # 对话会话 ID（新增）
    folder_ids: Optional[list[int]] = None  # 指定收藏夹，None 表示全部


class ChatResponse(BaseModel):
    """对话响应"""
    answer: str
    sources: list[dict]  # 来源视频列表


# ==================== 会话管理 Pydantic 模型 ====================

class ChatSessionInfo(BaseModel):
    """会话信息"""
    chat_session_id: str
    title: Optional[str] = None
    folder_ids: Optional[list[int]] = None
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    is_archived: bool = False


class ChatSessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: list[ChatSessionInfo]
    total: int
    page: int
    page_size: int


class ChatSessionCreateResponse(BaseModel):
    """创建会话响应"""
    chat_session_id: str
    title: str
    created_at: datetime


class ChatMessageInfo(BaseModel):
    """消息信息"""
    id: int
    role: str
    content: str
    sources: Optional[list[dict]] = None
    route: Optional[str] = None
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    """消息列表响应"""
    messages: list[ChatMessageInfo]
    total: int
    page: int
    page_size: int


class ChatSessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    is_archived: Optional[bool] = None


class ConversationSearchResult(BaseModel):
    """对话搜索结果"""
    chat_session_id: str
    session_title: Optional[str] = None
    message_id: int
    content: str
    highlight: Optional[str] = None
    created_at: datetime


class ConversationSearchResponse(BaseModel):
    """对话搜索响应"""
    results: list[ConversationSearchResult]
    total: int
    page: int
    page_size: int


# ==================== 人工校正 Pydantic 模型 ====================

class CorrectionVideo(BaseModel):
    """待校正视频"""
    bvid: str
    title: str
    asr_quality_score: Optional[float] = None
    asr_quality_flags: Optional[list[str]] = None
    content_preview: Optional[str] = None
    is_corrected: bool = False
    created_at: datetime


class CorrectionListResponse(BaseModel):
    """校正列表响应"""
    videos: list[CorrectionVideo]
    total: int
    page: int
    page_size: int


class Sentence(BaseModel):
    """句子"""
    id: int
    text: str
    start: float
    end: float
    confidence: float
    is_flagged: bool = False


class QualityReport(BaseModel):
    """质量报告"""
    quality_score: float
    quality_grade: str  # excellent/good/medium/poor
    flags: list[str]
    confidence_avg: float
    confidence_min: float
    audio_quality: str  # good/medium/poor
    speech_ratio: float
    suggestions: list[str]


class CorrectionDetail(BaseModel):
    """校正详情"""
    bvid: str
    title: str
    content: str
    sentences: list[Sentence]
    quality_report: Optional[QualityReport] = None


class CorrectionSubmitRequest(BaseModel):
    """提交校正请求"""
    content: str
    corrected_sentences: Optional[list[dict]] = None


class CorrectionSubmitResponse(BaseModel):
    """校正提交响应"""
    success: bool
    message: str
    is_corrected: bool


class CorrectionHistoryItem(BaseModel):
    """校正历史项"""
    id: int
    original_content: str
    corrected_content: str
    char_diff: int
    word_diff: int
    correction_type: str
    created_at: datetime


class CorrectionHistoryResponse(BaseModel):
    """校正历史响应"""
    history: list[CorrectionHistoryItem]
    total: int
    page: int
    page_size: int
