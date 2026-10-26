"""
Bilibili RAG 知识库系统

数据库管理模块
"""
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from app.config import settings
from app.models import Base
import os


# 确保数据目录存在
os.makedirs("data", exist_ok=True)

SQLITE_BUSY_TIMEOUT_MS = 30_000


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """启用并发读写，并让短暂的写锁等待后重试。"""
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_database_engine(database_url: str, *, echo: bool = False):
    """创建带 SQLite 并发配置的异步数据库引擎。"""
    engine_options = {
        "echo": echo,
        "future": True,
    }
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000,
        }

    database_engine = create_async_engine(database_url, **engine_options)
    if database_url.startswith("sqlite"):
        event.listen(
            database_engine.sync_engine,
            "connect",
            _configure_sqlite_connection,
        )
    return database_engine


# 创建异步引擎
engine = create_database_engine(settings.database_url, echo=settings.debug)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """初始化数据库（创建表）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            columns = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns("video_cache")
            )
            if not any(column["name"] == "transcript_segments" for column in columns):
                await conn.exec_driver_sql(
                    "ALTER TABLE video_cache ADD COLUMN transcript_segments JSON"
                )


async def get_db() -> AsyncSession:
    """获取数据库会话（用于 FastAPI 依赖注入）"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context():
    """获取数据库会话（用于上下文管理器）"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
