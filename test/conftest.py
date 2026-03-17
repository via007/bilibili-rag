"""
Bilibili RAG 测试配置
提供测试所需的 fixtures
"""
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, ChatSession, ChatMessage

# pytest-asyncio 配置
pytest_plugins = ('pytest_asyncio',)


# 使用内存 SQLite 进行测试
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    """创建测试数据库引擎"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_db_with_data(test_db: AsyncSession) -> AsyncSession:
    """创建带有测试数据的数据库会话"""
    from datetime import datetime, timedelta

    # 创建测试用户会话
    user_session_id = "test_user_001"

    # 创建测试会话
    sessions = [
        ChatSession(
            session_id="session_001",
            user_session_id=user_session_id,
            title="测试会话1",
            folder_ids=[1, 2],
            message_count=2,
            last_message_at=datetime.utcnow() - timedelta(hours=1),
            is_archived=False,
            is_deleted=False,
        ),
        ChatSession(
            session_id="session_002",
            user_session_id=user_session_id,
            title="测试会话2",
            folder_ids=[1],
            message_count=1,
            last_message_at=datetime.utcnow() - timedelta(hours=2),
            is_archived=False,
            is_deleted=False,
        ),
        ChatSession(
            session_id="session_003",
            user_session_id=user_session_id,
            title="归档会话",
            folder_ids=None,
            message_count=0,
            is_archived=True,
            is_deleted=False,
        ),
        ChatSession(
            session_id="session_004",
            user_session_id="other_user",
            title="其他用户会话",
            folder_ids=None,
            message_count=0,
            is_archived=False,
            is_deleted=False,
        ),
    ]

    for session in sessions:
        test_db.add(session)

    # 创建测试消息
    messages = [
        ChatMessage(
            chat_session_id="session_001",
            role="user",
            content="测试问题1",
            sources=None,
            route="vector",
        ),
        ChatMessage(
            chat_session_id="session_001",
            role="assistant",
            content="测试回答1",
            sources=[{"bvid": "BV123", "title": "测试视频"}],
            route="vector",
        ),
        ChatMessage(
            chat_session_id="session_002",
            role="user",
            content="关于Python的问题",
            sources=None,
            route="direct",
        ),
    ]

    for message in messages:
        test_db.add(message)

    await test_db.commit()

    return test_db


@pytest.fixture
def test_user_session_id() -> str:
    """测试用户会话ID"""
    return "test_user_001"


@pytest.fixture
def test_chat_session_id() -> str:
    """测试会话ID"""
    return "session_001"
