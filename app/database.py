"""
Bilibili RAG 知识库系统

数据库管理模块
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from app.config import settings
from app.models import Base
import os


# 确保数据目录存在
os.makedirs("data", exist_ok=True)

# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True
)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """初始化数据库（创建表 + 自动迁移新列）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 自动迁移：为已有表添加新字段（SQLite 不支持 ALTER TABLE ADD COLUMN 已存在列，故用尝试式）
    await _migrate_add_columns()


async def _migrate_add_columns():
    """自动迁移：为已有表添加新增的列

    video_pages 新增: is_vectorized, vectorized_at, vector_chunk_count, vector_error
    user_settings 新增: asr_api_key_encrypted, asr_base_url, asr_model
    async_tasks 新增: (全新表，无迁移需求)
    """
    migrations = [
        # (table, column, type_with_default)
        ("video_pages", "is_vectorized", "VARCHAR(20) DEFAULT 'pending'"),
        ("video_pages", "vectorized_at", "TIMESTAMP"),
        ("video_pages", "vector_chunk_count", "INTEGER DEFAULT 0"),
        ("video_pages", "vector_error", "TEXT"),
        # Plan 0018: ASR credential columns
        ("user_settings", "asr_api_key_encrypted", "TEXT"),
        ("user_settings", "asr_base_url", "TEXT"),
        ("user_settings", "asr_model", "TEXT"),
        # Plan 0012: Quiz pages mode columns
        ("quiz_sets", "source_type", "VARCHAR(20) DEFAULT 'folder'"),
        ("quiz_sets", "source_pages", "TEXT"),
    ]

    for table, column, col_def in migrations:
        try:
            async with engine.begin() as conn:
                from sqlalchemy import text
                # SQLite: 检查列是否已存在
                result = await conn.execute(
                    text(f"PRAGMA table_info({table})")
                )
                existing_cols = [row[1] for row in result.fetchall()]
                if column not in existing_cols:
                    await conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                    )
                    from loguru import logger
                    logger.info(f"[MIGRATION] Added column {table}.{column}")
                else:
                    from loguru import logger
                    logger.debug(f"[MIGRATION] Column {table}.{column} already exists, skipping")
        except Exception as e:
            from loguru import logger
            logger.warning(f"[MIGRATION] Could not add {table}.{column}: {e}")


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
