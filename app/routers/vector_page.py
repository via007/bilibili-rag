"""
Bilibili RAG 知识库系统

分P向量化路由 - 4 个 API 接口
"""
import uuid
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    VideoPage,
    VectorPageStatusResponse, VectorPageTaskStatus,
    VectorPageCreateRequest, VectorPageReVectorRequest
)
from app.services.task_store import SQLiteTaskPersistence
from app.services.vector_page_service import VectorPageService
from app.services.rag import RAGService

router = APIRouter(prefix="/vec/page", tags=["VectorPage"])

# 全局单例
_task_store = SQLiteTaskPersistence()
_vector_service: Optional[VectorPageService] = None


def get_vector_service() -> VectorPageService:
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorPageService(_task_store)
    return _vector_service


def _build_task_id() -> str:
    return str(uuid.uuid4())


# ==================== API 接口 ====================

@router.get("/status")
async def get_vec_status(
    bvid: str,
    cid: int,
    db: AsyncSession = Depends(get_db)
) -> VectorPageStatusResponse:
    """
    查询分P向量状态（含 ChromaDB 校验 + steps）
    """
    # 1. 查 video_pages
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
    )
    page = result.scalar_one_or_none()

    if not page:
        return VectorPageStatusResponse(
            exists=False,
            is_processed=False,
            is_vectorized="pending",
            vector_chunk_count=0,
            chroma_exists=False,
        )

    # 2. 查 ChromaDB 实际数量
    rag = RAGService()
    chroma_count = rag.get_page_vector_count(bvid, page.page_index)

    # 3. ChromaDB 一致性修复
    chroma_exists = chroma_count > 0
    fixed_vectorized = page.is_vectorized

    if page.is_vectorized == "done" and chroma_count == 0:
        # DB says done but ChromaDB is empty → degrade to failed
        page.is_vectorized = "failed"
        page.vector_error = "ChromaDB 实际向量为空，数据可能损坏"
        await db.commit()
        fixed_vectorized = "failed"
        chroma_exists = False

    elif page.is_vectorized == "pending" and chroma_count > 0:
        # DB says pending but ChromaDB has data → upgrade to done
        page.is_vectorized = "done"
        from datetime import datetime
        page.vectorized_at = datetime.utcnow()
        page.vector_chunk_count = chroma_count
        await db.commit()
        fixed_vectorized = "done"
        chroma_exists = True

    # 4. 查 async_tasks.steps（如有）
    steps = None

    return VectorPageStatusResponse(
        exists=True,
        bvid=page.bvid,
        cid=page.cid,
        page_index=page.page_index,
        page_title=page.page_title,
        is_processed=page.is_processed,
        content_preview=(page.content or "")[:200] if page.content else None,
        is_vectorized=fixed_vectorized,
        vectorized_at=page.vectorized_at,
        vector_chunk_count=page.vector_chunk_count or chroma_count,
        vector_error=page.vector_error,
        chroma_exists=chroma_exists,
        steps=steps,
    )


@router.post("/create")
async def create_vec(
    req: VectorPageCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    幂等向量化（ASR 未完成则先 ASR）
    """
    # 1. 查 video_pages
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == req.bvid, VideoPage.cid == req.cid)
    )
    page = result.scalar_one_or_none()

    if not page:
        page = VideoPage(
            bvid=req.bvid,
            cid=req.cid,
            page_index=req.page_index,
            page_title=req.page_title or f"P{req.page_index + 1}",
            is_processed=False,
            version=1,
            is_vectorized="pending",
            vector_chunk_count=0,
        )
        db.add(page)
        await db.commit()
        await db.refresh(page)

    # 2. 幂等检查
    if page.is_vectorized == "done" and page.content:
        # 检查 content 是否变化（future: hash 比对）
        # 目前简单跳过
        return {"task_id": None, "message": "已是最新向量"}

    # 3. 创建 async_tasks → 后台执行
    task_id = _build_task_id()
    await _task_store.create(
        task_id=task_id,
        task_type="vec_page",
        target={
            "bvid": req.bvid,
            "cid": req.cid,
            "page_index": req.page_index,
            "page_title": req.page_title or page.page_title,
        }
    )

    # 启动后台任务
    asyncio.create_task(
        get_vector_service().process_page_vectorization(
            task_id=task_id,
            bvid=req.bvid,
            cid=req.cid,
            page_index=req.page_index,
            page_title=req.page_title or page.page_title or f"P{req.page_index + 1}",
        )
    )

    return {"task_id": task_id, "message": "向量化任务已创建"}


@router.post("/revector")
async def revector_vec(
    req: VectorPageReVectorRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    强制重建（删旧向量 + 新建）
    """
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == req.bvid, VideoPage.cid == req.cid)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="VideoPage not found")

    if not page.is_processed or not page.content:
        raise HTTPException(status_code=400, detail="ASR 未完成，无法向量化")

    # 标记 is_vectorized = pending（前置保护）
    page.is_vectorized = "pending"
    page.vector_error = None
    await db.commit()

    # 创建任务
    task_id = _build_task_id()
    await _task_store.create(
        task_id=task_id,
        task_type="vec_page",
        target={
            "bvid": req.bvid,
            "cid": req.cid,
            "page_index": page.page_index,
            "page_title": page.page_title,
        }
    )

    # 启动后台任务
    asyncio.create_task(
        get_vector_service().process_page_vectorization(
            task_id=task_id,
            bvid=req.bvid,
            cid=req.cid,
            page_index=page.page_index,
            page_title=page.page_title or f"P{page.page_index + 1}",
        )
    )

    return {"task_id": task_id, "message": "重建任务已创建"}


@router.get("/status/{task_id}")
async def get_vec_task_status(task_id: str) -> VectorPageTaskStatus:
    """
    轮询任务状态（含 steps 透传）
    """
    # 先查 async_tasks
    task = await _task_store.get(task_id)

    if not task:
        # 可能是 ASR 任务（存储在 asr_tasks 内存中）
        from app.routers.asr import asr_tasks
        asr_task = asr_tasks.get(task_id)
        if asr_task:
            return VectorPageTaskStatus(
                task_id=task_id,
                status=asr_task["status"],
                progress=asr_task["progress"],
                message=asr_task["message"],
                steps=[{"name": "asr", "status": asr_task["status"], "progress": asr_task["progress"]}],
            )
        raise HTTPException(status_code=404, detail="任务不存在")

    # 构建 message
    status = task["status"]
    if status == "done":
        message = "完成"
    elif status == "failed":
        message = f"失败: {task.get('error', 'unknown')}"
    elif status == "processing":
        message = "处理中..."
    else:
        message = "等待中"

    return VectorPageTaskStatus(
        task_id=task["task_id"],
        status=task["status"],
        progress=task.get("progress", 0),
        message=message,
        steps=task.get("steps"),
        result=task.get("result"),
        error=task.get("error"),
    )


# ==================== 内部函数 ====================

async def _trigger_asr_then_vec(
    asr_task_id: str,
    bvid: str,
    cid: int,
    page_index: int,
    page_title: str
):
    """ASR 完成后自动触发向量化"""
    from app.routers.asr import asr_tasks

    # 等待 ASR 完成（最多 5 分钟）
    for _ in range(300):
        task = asr_tasks.get(asr_task_id)
        if task and task["status"] in ("done", "failed"):
            break
        await asyncio.sleep(1)

    # ASR 成功后触发向量化
    vec_task_id = _build_task_id()
    await _task_store.create(
        task_id=vec_task_id,
        task_type="vec_page",
        target={
            "bvid": bvid,
            "cid": cid,
            "page_index": page_index,
            "page_title": page_title,
        }
    )

    await asyncio.sleep(1)  # 等待一点时间让 ASR 状态稳定

    asyncio.create_task(
        get_vector_service().process_page_vectorization(
            task_id=vec_task_id,
            bvid=bvid,
            cid=cid,
            page_index=page_index,
            page_title=page_title,
        )
    )
