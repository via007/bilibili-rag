"""
Bilibili RAG 知识库系统

ASR 路由 - 分P视频语音转文本
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    VideoPage, VideoPageVersion,
    ASRCreateRequest, ASRUpdateRequest, ASRReASRRequest,
    ASRContentResponse, ASRTaskStatus, VideoPageVersionInfo
)

router = APIRouter(prefix="/asr", tags=["ASR"])

# 内存任务状态存储
asr_tasks: dict = {}


def _create_task() -> str:
    """创建新任务并返回 task_id"""
    task_id = str(uuid.uuid4())
    asr_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "message": "任务已创建",
        "result": None,
    }
    return task_id


# ==================== 依赖注入 ====================

def get_ASRPageService():
    """延迟导入 ASRPageService，避免循环依赖"""
    from app.services.asr_page_service import ASRPageService
    return ASRPageService()


# ==================== API 接口 ====================

@router.get("/content")
async def get_asr_content(
    bvid: str,
    cid: int,
    db: AsyncSession = Depends(get_db)
) -> ASRContentResponse:
    """
    查询 ASR 内容
    - 不存在返回 {exists: false}
    - 存在返回内容详情
    """
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
    )
    page = result.scalar_one_or_none()

    if not page:
        return ASRContentResponse(exists=False)

    return ASRContentResponse(
        exists=True,
        bvid=page.bvid,
        cid=page.cid,
        page_index=page.page_index,
        page_title=page.page_title,
        content=page.content,
        content_source=page.content_source,
        version=page.version,
        is_processed=page.is_processed,
    )


@router.post("/create")
async def create_asr(
    req: ASRCreateRequest,
    db: AsyncSession = Depends(get_db),
    service = Depends(get_ASRPageService)
):
    """
    幂等创建 ASR 任务
    - 已存在且 is_processed=true → 直接返回
    - 不存在 → 创建记录 + 后台任务
    """
    # 查询是否已存在（唯一约束是 bvid+page_index，非 bvid+cid）
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == req.bvid, VideoPage.page_index == req.page_index)
    )
    existing = result.scalar_one_or_none()

    if existing and existing.is_processed:
        # 已完成，直接返回
        return {
            "task_id": None,
            "message": "ASR 已完成",
            "version": existing.version,
        }

    # 不存在则创建记录
    if not existing:
        new_page = VideoPage(
            bvid=req.bvid,
            cid=req.cid,
            page_index=req.page_index,
            page_title=req.page_title or f"P{req.page_index + 1}",
            is_processed=False,
            version=1,
        )
        db.add(new_page)
        await db.commit()

    # 创建后台任务
    task_id = _create_task()

    # 启动后台 ASR 处理
    import asyncio
    asyncio.create_task(
        service.process_page(
            task_id=task_id,
            bvid=req.bvid,
            cid=req.cid,
            page_index=req.page_index,
            page_title=req.page_title or f"P{req.page_index + 1}",
        )
    )

    return {"task_id": task_id, "message": "ASR 任务已创建"}


@router.post("/update")
async def update_asr_content(
    req: ASRUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    手动编辑更新（覆盖，不新建版本）
    """
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == req.bvid, VideoPage.page_index == req.page_index)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="ASR 记录不存在")

    # 覆盖内容，标记为用户编辑
    page.content = req.content
    page.content_source = "user_edit"
    page.is_processed = True
    page.updated_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "更新成功"}


@router.post("/reasr")
async def reasr(
    req: ASRReASRRequest,
    db: AsyncSession = Depends(get_db),
    service = Depends(get_ASRPageService)
):
    """
    强制重新 ASR（新建版本）
    """
    # 查询现有记录（唯一约束是 bvid+page_index，非 bvid+cid）
    result = await db.execute(
        select(VideoPage).where(VideoPage.bvid == req.bvid, VideoPage.page_index == req.page_index)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="ASR 记录不存在")

    # 旧版本 is_latest = false
    old_version = page.version

    # 插入新版本记录
    new_version_record = VideoPageVersion(
        bvid=req.bvid,
        cid=req.cid,
        page_index=page.page_index,
        version=old_version,
        content=page.content,
        content_source=page.content_source,
        is_latest=False,
    )
    db.add(new_version_record)

    # 更新 video_pages
    page.version = old_version + 1
    page.is_processed = False
    page.content = None  # 清空，等待新 ASR
    page.content_source = None
    page.updated_at = datetime.utcnow()

    await db.commit()

    # 创建后台任务
    task_id = _create_task()

    # 启动后台 ASR 处理
    import asyncio
    asyncio.create_task(
        service.process_page(
            task_id=task_id,
            bvid=req.bvid,
            cid=req.cid,
            page_index=page.page_index,
            page_title=page.page_title or f"P{page.page_index + 1}",
        )
    )

    return {"task_id": task_id, "message": "重新 ASR 已启动"}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str) -> ASRTaskStatus:
    """轮询任务状态"""
    if task_id not in asr_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = asr_tasks[task_id]
    return ASRTaskStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
    )


@router.get("/versions")
async def get_versions(
    bvid: str,
    cid: int,
    db: AsyncSession = Depends(get_db)
) -> list[VideoPageVersionInfo]:
    """查询版本历史"""
    result = await db.execute(
        select(VideoPageVersion)
        .where(VideoPageVersion.bvid == bvid, VideoPageVersion.cid == cid)
        .order_by(VideoPageVersion.version.desc())
    )
    versions = result.scalars().all()

    return [
        VideoPageVersionInfo(
            version=v.version,
            content_source=v.content_source or "unknown",
            content_preview=(v.content or "")[:100],
            is_latest=v.is_latest,
            created_at=v.created_at,
        )
        for v in versions
    ]
