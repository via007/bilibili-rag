"""
Bilibili RAG 知识库系统

主应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys
import os

from app.config import settings, ensure_directories

# === 将 .env 中的 LangSmith 配置同步到 os.environ ===
# langchain 在首次导入时检查 os.environ 以决定是否注册自动追踪回调。
# pydantic_settings 读取 .env 后不会自动写回 os.environ，因此必须手动同步。
if settings.langchain_tracing_v2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
if settings.langsmith_tracing:
    os.environ["LANGSMITH_TRACING"] = "true"
if settings.langsmith_api_key:
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
if settings.langsmith_project:
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
if settings.langsmith_endpoint:
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint

from app.database import init_db
from app.routers import auth, favorites, knowledge, chat
from app.routers.asr import router as asr_router
from app.routers.vector_page import router as vector_page_router


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.debug else "INFO"
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG"
)


# === LangSmith 追踪诊断（必须在 langchain 首次导入之前执行） ===
# LangSmith 的自动追踪由 langchain 包在首次导入时检查环境变量并注册。
# 不需要也不应该手动 import langsmith 来"注册"追踪器。
def _diagnose_langsmith() -> None:
    tracing_v2 = os.environ.get("LANGCHAIN_TRACING_V2", "").lower()
    langsmith_tracing = os.environ.get("LANGSMITH_TRACING", "").lower()
    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    project = os.environ.get("LANGSMITH_PROJECT", "default")

    is_enabled = tracing_v2 == "true" or langsmith_tracing == "true"

    if not is_enabled:
        logger.info(
            "[LANGSMITH] 追踪未启用。"
            "设置 LANGCHAIN_TRACING_V2=true 或 LANGSMITH_TRACING=true 以启用自动追踪。"
        )
        return

    if not api_key:
        logger.warning(
            "[LANGSMITH] 追踪已启用但 LANGSMITH_API_KEY 未设置。"
            "请在 .env 中配置 API key。"
        )
        return

    logger.info(f"[LANGSMITH] 自动追踪已启用 (project={project})")

    # 检查 langsmith 包是否安装
    try:
        import langsmith as ls
        logger.info(f"[LANGSMITH] langsmith 包已安装 (版本: {ls.__version__})")
    except ImportError:
        logger.error(
            "[LANGSMITH] 追踪已启用但 langsmith 包未安装!"
            "请运行: pip install langsmith"
        )
        return

    # 验证 API key 是否有效
    try:
        from langsmith import Client
        client = Client()
        projects = list(client.list_projects())
        logger.info(f"[LANGSMITH] API key 验证成功 (找到 {len(projects)} 个项目)")
    except Exception as exc:
        logger.warning(f"[LANGSMITH] API key 验证失败: {exc}")


diagnose_langsmith = _diagnose_langsmith


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 Bilibili RAG 知识库系统启动中...")
    ensure_directories()
    await init_db()
    logger.info("✅ 数据库初始化完成")

    # LangSmith 追踪诊断
    diagnose_langsmith()

    # 初始化 QueryRewriter
    from app.services.query import QueryRewriter
    app.state.rewriter = QueryRewriter()
    logger.info("[QUERY_REWRITE] QueryRewriter initialized")

    # === 崩溃恢复：扫描 pending 向量化任务 ===
    import asyncio
    from app.services.task_store import SQLiteTaskPersistence
    from app.services.vector_page_service import VectorPageService

    task_store = SQLiteTaskPersistence()
    vector_service = VectorPageService(task_store)
    pending = await task_store.list_pending("vec_page")

    if pending:
        logger.info(f"[STARTUP] 发现 {len(pending)} 个未完成的向量化任务，开始恢复...")
        for task in pending:
            asyncio.create_task(
                vector_service.process_page_vectorization(
                    task_id=task["task_id"],
                    bvid=task["target"]["bvid"],
                    cid=task["target"]["cid"],
                    page_index=task["target"]["page_index"],
                    page_title=task["target"].get("page_title"),
                )
            )

    yield

    # 关闭时
    await app.state.rewriter.close()
    logger.info("[QUERY_REWRITE] QueryRewriter shutdown")
    logger.info("👋 应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="Bilibili RAG 知识库系统",
    description="""
## 项目简介

将你的 B站收藏夹变成可对话的知识库！

### 功能特性

- 🔐 **B站扫码登录** - 安全便捷
- 📁 **收藏夹管理** - 查看和选择收藏夹
- 🤖 **AI 内容提取** - 自动获取视频摘要/字幕
- 💬 **智能问答** - 基于收藏内容回答问题
- 🔍 **语义搜索** - 快速找到相关视频

### 技术栈

- FastAPI + LangChain + ChromaDB
- B站 API (非官方)
    """,
    version="0.1.0",
    lifespan=lifespan
)


# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
app.include_router(auth.router)
app.include_router(favorites.router)
app.include_router(knowledge.router)
app.include_router(chat.router)
app.include_router(asr_router)
app.include_router(vector_page_router)


@app.get("/")
async def root():
    """API 根路径"""
    return {
        "message": "🎬 Bilibili RAG 知识库系统",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )
