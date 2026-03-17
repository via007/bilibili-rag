"""
Bilibili RAG 知识库系统

智能摘要路由 - 视频摘要生成与获取
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/knowledge/summary", tags=["知识库-智能摘要"])


# ============== 响应模型 ==============

class VideoSummaryResponse(BaseModel):
    """视频摘要响应"""
    bvid: str
    title: Optional[str] = None
    short_intro: Optional[str] = None
    key_points: Optional[List[str]] = None
    target_audience: Optional[str] = None
    difficulty_level: Optional[str] = None
    tags: Optional[List[str]] = None
    is_generated: bool = False
    generated_at: Optional[datetime] = None


class SummaryGenerateRequest(BaseModel):
    """手动生成摘要请求"""
    bvid: str


class SummaryGenerateResponse(BaseModel):
    """生成摘要响应"""
    bvid: str
    message: str
    task_id: Optional[str] = None


# ============== 辅助函数 ==============

async def get_video_summary_from_db(db: AsyncSession, bvid: str) -> Optional[dict]:
    """从数据库获取视频摘要"""
    # 尝试从 video_summaries 表获取
    try:
        from app.models import VideoSummaryDB
        result = await db.execute(
            select(VideoSummaryDB).where(VideoSummaryDB.bvid == bvid)
        )
        summary = result.scalar_one_or_none()
        if summary:
            return {
                "bvid": summary.bvid,
                "short_intro": summary.short_intro,
                "key_points": summary.key_points,
                "target_audience": summary.target_audience,
                "difficulty_level": summary.difficulty_level,
                "tags": summary.tags,
                "is_generated": summary.is_generated,
                "generated_at": summary.generated_at,
            }
    except Exception as e:
        logger.debug(f"查询 video_summaries 表失败: {e}")

    # 尝试从 VideoCache 获取摘要 JSON
    try:
        from app.models import VideoCache
        result = await db.execute(
            select(VideoCache).where(VideoCache.bvid == bvid)
        )
        cache = result.scalar_one_or_none()
        if cache and cache.summary_json:
            return {
                "bvid": bvid,
                "title": cache.title,
                **cache.summary_json,
                "is_generated": bool(cache.summary_json.get("short_intro")),
                "generated_at": cache.updated_at,
            }
    except Exception as e:
        logger.debug(f"查询 VideoCache 表失败: {e}")

    return None


async def generate_summary_task(bvid: str):
    """后台生成摘要任务"""
    try:
        from app.services.summary import SummaryService
        from app.database import get_db_context

        summary_service = SummaryService(temperature=0.3)

        async with get_db_context() as db:
            # 获取视频内容
            from app.models import VideoCache
            result = await db.execute(
                select(VideoCache).where(VideoCache.bvid == bvid)
            )
            cache = result.scalar_one_or_none()

            if not cache:
                logger.warning(f"视频 {bvid} 不存在，无法生成摘要")
                return

            if not cache.content or len(cache.content.strip()) < 100:
                logger.warning(f"视频 {bvid} 内容太短，无法生成摘要")
                return

            # 生成摘要
            summary = await summary_service.generate_summary(
                title=cache.title,
                content=cache.content,
                bvid=bvid
            )

            # 保存摘要
            from app.models import VideoSummaryDB
            existing = await db.execute(
                select(VideoSummaryDB).where(VideoSummaryDB.bvid == bvid)
            )
            db_summary = existing.scalar_one_or_none()

            if db_summary:
                db_summary.short_intro = summary.short_intro
                db_summary.key_points = summary.key_points
                db_summary.target_audience = summary.target_audience
                db_summary.difficulty_level = summary.difficulty_level
                db_summary.tags = summary.tags
                db_summary.is_generated = True
                db_summary.generated_at = datetime.utcnow()
            else:
                db_summary = VideoSummaryDB(
                    bvid=bvid,
                    short_intro=summary.short_intro,
                    key_points=summary.key_points,
                    target_audience=summary.target_audience,
                    difficulty_level=summary.difficulty_level,
                    tags=summary.tags,
                    is_generated=True,
                    generated_at=datetime.utcnow(),
                )
                db.add(db_summary)

            # 同时更新 VideoCache 的 summary_json
            cache.summary_json = {
                "short_intro": summary.short_intro,
                "key_points": summary.key_points,
                "target_audience": summary.target_audience,
                "difficulty_level": summary.difficulty_level,
                "tags": summary.tags,
            }

            await db.commit()
            logger.info(f"视频 {bvid} 摘要生成完成")

    except Exception as e:
        logger.error(f"生成摘要失败 [{bvid}]: {e}")


# ============== API 路由 ==============

@router.get("/{bvid}", response_model=VideoSummaryResponse)
async def get_video_summary(
    bvid: str,
    db: AsyncSession = Depends(get_db),
):
    """获取视频摘要"""
    summary_data = await get_video_summary_from_db(db, bvid)

    if not summary_data:
        raise HTTPException(status_code=404, detail=f"视频 {bvid} 暂无摘要")

    # 获取视频标题
    from app.models import VideoCache
    result = await db.execute(
        select(VideoCache.title).where(VideoCache.bvid == bvid)
    )
    title = result.scalar()

    return VideoSummaryResponse(
        bvid=bvid,
        title=title,
        short_intro=summary_data.get("short_intro"),
        key_points=summary_data.get("key_points"),
        target_audience=summary_data.get("target_audience"),
        difficulty_level=summary_data.get("difficulty_level"),
        tags=summary_data.get("tags"),
        is_generated=summary_data.get("is_generated", False),
        generated_at=summary_data.get("generated_at"),
    )


@router.post("/generate", response_model=SummaryGenerateResponse)
async def generate_summary(
    request: SummaryGenerateRequest,
    background_tasks: BackgroundTasks,
):
    """手动生成视频摘要"""
    bvid = request.bvid

    # 检查服务是否可用
    try:
        from app.services.llm_factory import get_llm_client as get_llm
        llm = get_llm()
    except Exception as e:
        logger.error(f"LLM 服务不可用: {e}")
        raise HTTPException(status_code=503, detail="LLM 服务暂不可用")

    # 使用后台任务处理
    background_tasks.add_task(generate_summary_task, bvid)

    return SummaryGenerateResponse(
        bvid=bvid,
        message="摘要生成任务已提交，请在稍后查询结果",
    )
