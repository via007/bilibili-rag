"""
Bilibili RAG 知识库系统

分P向量化服务 - 原子性保护 + steps 透传
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select

from app.database import get_db_context
from app.models import VideoPage, VideoContent, ContentSource
from app.services.rag import RAGService
from app.services.task_store import TaskPersistence


class VectorPageService:
    """
    分P向量化服务

    职责：
    1. 向量化状态管理（pending 原子性保护）
    2. ASR + 向量化串联（如 ASR 未完成）
    3. ChromaDB per-page 向量操作
    4. steps 进度透传
    """

    def __init__(self, task_store: TaskPersistence):
        self.rag = RAGService()
        self.task_store = task_store

    async def process_page_vectorization(
        self,
        task_id: str,
        bvid: str,
        cid: int,
        page_index: int,
        page_title: Optional[str] = None,
    ):
        """
        v2 原子性流程：
        1. 前置保护：is_vectorized = "pending"
        2. [可选] ASR 阶段（content 无时）
        3. 删除旧向量
        4. 写入新向量
        5. 后置确认：is_vectorized = "done"
        """
        try:
            # === Phase 0: 初始化 steps ===
            await self.task_store.update(
                task_id,
                steps=[{"name": "init", "status": "processing", "progress": 0}]
            )

            # === Phase 1: 前置保护 + 幂等检查 ===
            async with get_db_context() as db:
                result = await db.execute(
                    select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                )
                page = result.scalar_one_or_none()
                if not page:
                    raise Exception(f"VideoPage not found: bvid={bvid}, cid={cid}")

                # 幂等检查：已是 done 且 content 未变化
                if page.is_vectorized == "done" and not self._content_changed(page):
                    await self.task_store.update(
                        task_id,
                        status="done",
                        progress=100,
                        result={"skipped": True, "message": "已是最新"}
                    )
                    return

                # 前置保护：标记 pending（昭告天下"正在重建"）
                page.is_vectorized = "pending"
                page.vector_error = None
                await db.commit()

            await self.task_store.update(
                task_id,
                progress=10,
                steps=[{"name": "init", "status": "done", "progress": 100}]
            )

            # === Phase 2: ASR（如需要）===
            if not page.is_processed or not page.content:
                await self.task_store.update(
                    task_id,
                    steps=[
                        {"name": "init", "status": "done", "progress": 100},
                        {"name": "asr", "status": "processing", "progress": 0}
                    ]
                )
                await self._run_asr(bvid, cid, page_index, page_title or page.page_title or f"P{page_index + 1}")
                await self.task_store.update(
                    task_id,
                    steps=[
                        {"name": "init", "status": "done", "progress": 100},
                        {"name": "asr", "status": "done", "progress": 100}
                    ]
                )

            # === Phase 3: 删除旧向量 ===
            await self.task_store.update(
                task_id,
                progress=40,
                steps=[{"name": "vec", "status": "processing", "progress": 30}]
            )
            try:
                self._delete_page_vectors(bvid, page_index)
            except Exception as e:
                logger.warning(f"[{bvid}] 删除旧向量失败: {e}")

            # === Phase 4: 写入新向量 ===
            await self.task_store.update(task_id, progress=60)

            # 重新读取最新 content（ASR 可能已更新）
            async with get_db_context() as db:
                result = await db.execute(
                    select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                )
                page = result.scalar_one_or_none()
                if not page or not page.content:
                    raise Exception(f"VideoPage content is empty after ASR: bvid={bvid}, cid={cid}")

                text = page.content
                title = page_title or page.page_title or f"P{page_index + 1}"

                video = VideoContent(
                    bvid=bvid,
                    title=title,
                    content=text,
                    source=ContentSource.ASR,
                )

            chunk_count = self.rag.add_video_content(
                video=video,
                page_index=page_index,
                page_title=title,
            )

            # === Phase 5: 后置确认（原子提交）===
            async with get_db_context() as db:
                result = await db.execute(
                    select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                )
                page = result.scalar_one_or_none()
                page.is_vectorized = "done"
                page.vectorized_at = datetime.utcnow()
                page.vector_chunk_count = chunk_count
                await db.commit()

            await self.task_store.update(
                task_id,
                status="done",
                progress=100,
                steps=[{"name": "vec", "status": "done", "progress": 100}],
                result={"chunk_count": chunk_count}
            )
            logger.info(f"[VecPage] 完成 bvid={bvid}, cid={cid}, chunks={chunk_count}")

        except Exception as e:
            logger.error(f"[VecPage] 失败 bvid={bvid}, cid={cid}: {e}")
            await self.task_store.update(
                task_id,
                status="failed",
                error=str(e)
            )
            # 尝试标记 page 为 failed
            try:
                async with get_db_context() as db:
                    result = await db.execute(
                        select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                    )
                    page = result.scalar_one_or_none()
                    if page:
                        page.is_vectorized = "failed"
                        page.vector_error = str(e)
                        await db.commit()
            except Exception as db_err:
                logger.error(f"[VecPage] 更新 page 状态失败: {db_err}")
            raise

    async def _run_asr(self, bvid: str, cid: int, page_index: int, page_title: str):
        """执行 ASR（复用 ASRPageService）"""
        from app.services.asr_page_service import ASRPageService
        from app.routers.asr import asr_tasks

        service = ASRPageService()
        task_id = str(uuid.uuid4())
        asr_tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "ASR 任务已创建"
        }

        await service.process_page(
            task_id=task_id,
            bvid=bvid,
            cid=cid,
            page_index=page_index,
            page_title=page_title,
        )

        # 轮询 ASR 完成（最多等 5 分钟）
        for _ in range(300):
            task = asr_tasks.get(task_id)
            if task and task["status"] in ("done", "failed"):
                if task["status"] == "failed":
                    raise Exception(f"ASR failed: {task.get('message', 'unknown')}")
                break
            await asyncio.sleep(1)

    def _delete_page_vectors(self, bvid: str, page_index: int):
        """删除指定分P向量（而非整个 bvid）"""
        self.rag.delete_page_vectors(bvid, page_index)

    def _content_changed(self, page: VideoPage) -> bool:
        """检测 content 是否变化（用于幂等判断）"""
        # future: 可存储 content hash 比对
        return False
