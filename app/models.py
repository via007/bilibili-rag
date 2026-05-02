"""
Bilibili RAG 知识库系统

数据模型定义
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Float, UniqueConstraint
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


class ChatSession(Base):
    """聊天会话表"""
    __tablename__ = 'chat_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(String(64), unique=True, index=True, nullable=False)
    session_id = Column(String(64), index=True, nullable=False)  # 登录态 session
    title = Column(String(200), nullable=True)
    status = Column(String(20), default="active")  # active / archived / deleted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    """聊天消息表"""
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(String(64), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False, default="")
    status = Column(String(20), default="completed")  # pending / completed / failed
    sources = Column(JSON, nullable=True)  # 来源列表
    tokens_used = Column(Integer, nullable=True)
    model = Column(String(100), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


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


# ==================== Pydantic 模型 (聊天历史) ====================

class ChatSessionCreateRequest(BaseModel):
    """创建聊天会话请求"""
    session_id: str
    title: Optional[str] = None


class ChatSessionUpdateRequest(BaseModel):
    """更新聊天会话请求"""
    title: str


class ChatSessionResponse(BaseModel):
    """聊天会话响应"""
    id: int
    chat_session_id: str
    session_id: str
    title: Optional[str] = None
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """聊天消息响应"""
    id: int
    chat_session_id: str
    role: str
    content: str
    status: str = "completed"
    sources: Optional[list[dict]] = None
    tokens_used: Optional[int] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryQueryParams(BaseModel):
    """查询聊天历史参数"""
    chat_session_id: str
    page: int = 1
    page_size: int = 50


class ChatHistoryResponse(BaseModel):
    """聊天历史分页响应"""
    messages: list[ChatMessageResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class ChatSessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: list[ChatSessionResponse]


class ChatRequest(BaseModel):
    """对话请求（更新版，增加 chat_session_id）"""
    question: str
    session_id: Optional[str] = None        # 登录态（鉴权）
    chat_session_id: Optional[str] = None   # 聊天会话（新增）
    folder_ids: Optional[list[int]] = None  # 指定收藏夹，None 表示全部
    workspace_pages: Optional[list[WorkspacePage]] = None  # 工作区选中的分P
    mode: str = "standard"  # standard / agentic


# ==================== SQLAlchemy 模型 (用户 API Key) ====================

class UserSettings(Base):
    """用户自定义 API Key 配置表"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    # LLM 配置（Key 密文存储）
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_base_url = Column(Text, nullable=True)
    llm_model = Column(Text, nullable=True)
    # Embedding 配置（Key 密文存储）
    embedding_api_key_encrypted = Column(Text, nullable=True)
    embedding_base_url = Column(Text, nullable=True)
    embedding_model = Column(Text, nullable=True)
    # ASR 配置（Key 密文存储）
    asr_api_key_encrypted = Column(Text, nullable=True)
    asr_base_url = Column(Text, nullable=True)
    asr_model = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==================== Pydantic 模型 (用户 API Key) ====================

class ApiKeySetRequest(BaseModel):
    """API Key 配置请求（支持部分更新，null = 不修改）"""
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_model: Optional[str] = None
    asr_api_key: Optional[str] = None
    asr_base_url: Optional[str] = None
    asr_model: Optional[str] = None


class ApiKeyStatusResponse(BaseModel):
    """API Key 配置状态（不包含完整 Key）"""
    llm_is_configured: bool = False
    llm_masked_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_is_configured: bool = False
    embedding_masked_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_model: Optional[str] = None
    asr_is_configured: bool = False
    asr_masked_key: Optional[str] = None
    asr_base_url: Optional[str] = None
    asr_model: Optional[str] = None
    updated_at: Optional[datetime] = None


# ==================== SQLAlchemy 模型 (多 Provider Credential) ====================

class UserCredential(Base):
    """用户多 Provider API Key 配置表"""
    __tablename__ = "user_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    name = Column(String(64), nullable=False)          # 用户自定义名称，如 "我的 OpenAI"
    provider = Column(String(32), nullable=False)       # openai / anthropic / deepseek / custom
    api_key_encrypted = Column(Text, nullable=False)
    base_url = Column(Text, nullable=True)
    default_model = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CredentialUsage(Base):
    """凭证用量记录表"""
    __tablename__ = "credential_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    credential_id = Column(Integer, nullable=True)      # NULL = 系统默认 Key
    provider = Column(String(32), nullable=True)
    model = Column(String(64), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    api_calls = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== SQLAlchemy 模型 (Quiz 题目训练系统) ====================

class QuizSet(Base):
    """题目集"""
    __tablename__ = 'quiz_sets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_uuid = Column(String(64), unique=True, index=True, nullable=False)
    session_id = Column(String(64), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    question_count = Column(Integer, default=10)
    type_distribution = Column(JSON, nullable=True)  # {"single_choice": 3, "multi_choice": 2, ...}
    difficulty = Column(String(20), default='medium')  # easy / medium / hard
    folder_ids = Column(JSON, nullable=True)  # [1, 2, 3]
    source_type = Column(String(20), default="folder")  # "folder" / "pages"
    source_pages = Column(JSON, nullable=True)  # [{"bvid":"BVxxx","cid":123,"page_index":0,"page_title":"P1"}]
    bvid_count = Column(Integer, default=0)
    status = Column(String(20), default='generating')  # generating / done / failed
    error_message = Column(Text, nullable=True)
    total_score = Column(Integer, default=100)
    passing_score = Column(Integer, default=60)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QuizQuestion(Base):
    """题目明细"""
    __tablename__ = 'quiz_questions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_uuid = Column(String(64), index=True, nullable=False)
    question_uuid = Column(String(64), unique=True, index=True, nullable=False)
    bvid = Column(String(20), nullable=True)
    chunk_id = Column(String(20), nullable=True)
    source_segment = Column(Text, nullable=True)
    question_type = Column(String(20), nullable=False)  # single_choice / multi_choice / short_answer / essay
    difficulty = Column(String(20), default='medium')
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)  # ["A. 选项1", "B. 选项2", ...]
    correct_answer = Column(JSON, nullable=False)  # "A" or ["A", "C"] or "答案文本"
    explanation = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)  # ["关键词1", "关键词2"]
    answer_template = Column(Text, nullable=True)
    scoring_rubric = Column(JSON, nullable=True)  # [{"step": "...", "points": 2, "keywords": [...]}]
    model_answer = Column(Text, nullable=True)
    metadata_extra = Column(JSON, nullable=True)  # 避免与 SQLAlchemy MetaData 冲突
    is_valid = Column(Boolean, default=True)
    invalid_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class QuizSubmission(Base):
    """提交记录"""
    __tablename__ = 'quiz_submissions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_uuid = Column(String(64), unique=True, index=True, nullable=False)
    quiz_uuid = Column(String(64), index=True, nullable=False)
    session_id = Column(String(64), index=True, nullable=False)
    total_score = Column(Integer, nullable=True)
    auto_score = Column(Integer, nullable=True)
    manual_score = Column(Integer, nullable=True)
    passing_score = Column(Integer, nullable=True)
    is_complete = Column(Boolean, default=False)
    is_passed = Column(Boolean, nullable=True)
    correct_count = Column(Integer, default=0)
    total_question_count = Column(Integer, default=0)
    time_spent_seconds = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    graded_at = Column(DateTime, nullable=True)


class QuizAnswer(Base):
    """答案明细"""
    __tablename__ = 'quiz_answers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_uuid = Column(String(64), index=True, nullable=False)
    question_uuid = Column(String(64), index=True, nullable=False)
    question_type = Column(String(20), nullable=False)
    user_answer = Column(JSON, nullable=False)  # "A" or ["A", "C"] or "文本答案"
    user_answer_text = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    auto_score = Column(Integer, nullable=True)
    manual_score = Column(Integer, nullable=True)
    final_score = Column(Integer, nullable=True)
    correct_answer_snapshot = Column(JSON, nullable=False)  # 批改时的正确答案快照
    matched_keywords = Column(JSON, nullable=True)
    keyword_match_rate = Column(Float, nullable=True)
    grading_detail = Column(JSON, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    graded_at = Column(DateTime, nullable=True)


# ==================== Pydantic 模型 (多 Provider Credential) ====================

class CredentialCreate(BaseModel):
    """新建 Credential 请求"""
    name: str
    provider: str           # openai | anthropic | deepseek | custom
    api_key: str            # 明文，服务端加密
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: bool = False


class CredentialUpdate(BaseModel):
    """更新 Credential 请求（部分更新）"""
    name: Optional[str] = None
    api_key: Optional[str] = None       # 传了才更新
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: Optional[bool] = None


class CredentialResponse(BaseModel):
    """Credential 列表项响应（不包含完整 Key）"""
    id: int
    name: str
    provider: str
    masked_key: str                     # "sk-abc...4f2a"
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProviderUsage(BaseModel):
    """按 Provider 聚合的用量"""
    provider: str
    total_tokens: int
    api_calls: int
    cost_estimate: float = 0.0          # 预估费用（暂为 0）


class CredentialUsageItem(BaseModel):
    """按 Credential 聚合的用量"""
    credential_id: Optional[int] = None  # None = 系统默认
    name: str
    provider: str
    total_tokens: int
    api_calls: int
    cost_estimate: float = 0.0


class UsageSummary(BaseModel):
    """用量汇总响应"""
    total_tokens: int
    total_api_calls: int
    by_provider: list[ProviderUsage]     # 饼图数据
    by_credential: list[CredentialUsageItem]  # 树状图数据


# ==================== Pydantic 模型 (Quiz 题目训练系统) ====================

class QuestionType(str, Enum):
    """题型枚举"""
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"


class QuizGenerateRequest(BaseModel):
    """POST /quiz/generate 请求"""
    folder_ids: Optional[list[int]] = None
    pages: Optional[list[dict]] = None  # [{"bvid":"BVxxx","cid":123,"page_index":0,"page_title":"P1"}]
    question_count: int = 10
    type_distribution: Optional[dict[str, int]] = None
    difficulty: str = "medium"  # easy / medium / hard
    title: Optional[str] = None


class QuizGenerateResponse(BaseModel):
    """POST /quiz/generate 响应"""
    quiz_uuid: str
    question_count: int
    estimated_cost_tokens: int


class QuizQuestionResponse(BaseModel):
    """题目响应（不含答案）"""
    question_uuid: str
    question_type: str
    difficulty: str
    question_text: str
    options: Optional[list[str]] = None


class QuizSetResponse(BaseModel):
    """GET /quiz/{quiz_uuid} 响应"""
    quiz_uuid: str
    title: str
    status: str
    question_count: int
    type_distribution: Optional[dict] = None
    difficulty: str
    total_score: int
    passing_score: int
    created_at: datetime
    questions: list[QuizQuestionResponse] = []


class QuizAnswerItem(BaseModel):
    """提交答案项"""
    question_uuid: str
    answer: str | list[str]


class QuizSubmissionRequest(BaseModel):
    """POST /quiz/submit 请求"""
    quiz_uuid: str
    answers: list[QuizAnswerItem]
    time_spent_seconds: Optional[int] = None


class QuizAnswerResult(BaseModel):
    """单题批改结果"""
    question_uuid: str
    is_correct: Optional[bool] = None
    auto_score: Optional[int] = None
    correct_answer: str | list[str]
    grading_note: Optional[str] = None


class QuizSubmissionResponse(BaseModel):
    """POST /quiz/submit 响应"""
    submission_uuid: str
    score: Optional[int] = None
    passed: Optional[bool] = None
    correct_count: int
    total_count: int
    results: list[QuizAnswerResult]


class QuizHistoryItem(BaseModel):
    """答题历史项"""
    submission_uuid: str
    quiz_uuid: str
    title: str
    score: Optional[int] = None
    passed: Optional[bool] = None
    correct_count: int
    total_question_count: int
    time_spent_seconds: Optional[int] = None
    submitted_at: str


class QuizHistoryResponse(BaseModel):
    """答题历史响应"""
    submissions: list[QuizHistoryItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class WrongAnswerItem(BaseModel):
    """错题项"""
    question_uuid: str
    quiz_uuid: str
    question_type: str
    question_text: str
    options: Optional[list[str]] = None
    user_answer: str | list[str]
    correct_answer: str | list[str]
    explanation: Optional[str] = None
    times_wrong: int
    last_attempt_at: str


class WrongAnswerResponse(BaseModel):
    """错题响应"""
    wrong_answers: list[WrongAnswerItem]
    total: int
