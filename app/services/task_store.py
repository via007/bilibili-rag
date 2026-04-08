"""
Bilibili RAG 知识库系统

任务持久化层 - TaskPersistence 接口 + SQLite 实现
支持 future 替换为 Redis 实现
"""
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

from sqlalchemy import select
from loguru import logger

from app.database import get_db_context
from app.models import AsyncTask


class TaskPersistence(ABC):
    """任务存储抽象接口 — future 可替换为 Redis 实现"""

    @abstractmethod
    async def create(self, task_id: str, task_type: str, target: dict) -> None: ...

    @abstractmethod
    async def update(self, task_id: str, **kwargs) -> None: ...

    @abstractmethod
    async def get(self, task_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def list_pending(self, task_type: str) -> list[dict]: ...


class SQLiteTaskPersistence(TaskPersistence):
    """SQLite 实现（当前版本）"""

    async def create(self, task_id: str, task_type: str, target: dict) -> None:
        """创建新任务"""
        async with get_db_context() as db:
            task = AsyncTask(
                task_id=task_id,
                task_type=task_type,
                target=target,
                status="pending",
                progress=0,
                steps=None,
            )
            db.add(task)
            await db.commit()
            logger.debug(f"[TaskStore] 创建任务 task_id={task_id}, type={task_type}")

    async def update(self, task_id: str, **kwargs) -> None:
        """更新任务状态和字段"""
        async with get_db_context() as db:
            result = await db.execute(
                select(AsyncTask).where(AsyncTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.warning(f"[TaskStore] 任务不存在 task_id={task_id}")
                return

            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = datetime.utcnow()

            if kwargs.get("status") in ("done", "failed"):
                task.completed_at = datetime.utcnow()

            await db.commit()
            logger.debug(f"[TaskStore] 更新任务 task_id={task_id}, kwargs={kwargs}")

    async def get(self, task_id: str) -> Optional[dict]:
        """获取任务详情"""
        async with get_db_context() as db:
            result = await db.execute(
                select(AsyncTask).where(AsyncTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "target": task.target,
                "status": task.status,
                "progress": task.progress,
                "steps": task.steps,
                "result": task.result,
                "error": task.error,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "completed_at": task.completed_at,
            }

    async def list_pending(self, task_type: str) -> list[dict]:
        """扫描所有 pending/processing 任务（用于崩溃恢复）"""
        async with get_db_context() as db:
            result = await db.execute(
                select(AsyncTask)
                .where(AsyncTask.task_type == task_type)
                .where(AsyncTask.status.in_(["pending", "processing"]))
            )
            tasks = result.scalars().all()
            return [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "target": t.target,
                    "status": t.status,
                }
                for t in tasks
            ]


# ==================== Redis 预留接口（future 实现） ====================
# class RedisTaskPersistence(TaskPersistence):
#     """Redis 实现（future，替换此类不动业务代码）"""
#     async def create(self, task_id: str, task_type: str, target: dict) -> None: ...
#     async def update(self, task_id: str, **kwargs) -> None: ...
#     async def get(self, task_id: str) -> Optional[dict]: ...
#     async def list_pending(self, task_type: str) -> list[dict]: ...
