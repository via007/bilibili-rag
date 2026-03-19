"""
Bilibili RAG 知识库系统

知识库路由 - 构建和管理知识库
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional, Callable
from pydantic import BaseModel
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_context
from app.models import FavoriteFolder, FavoriteVideo, VideoCache, UserSession, ContentSource, VideoContent, ASRQualityLog
from app.services.bilibili import BilibiliService
from app.services.content_fetcher import ContentFetcher
from app.services.asr import ASRService
from app.services.rag import RAGService
from app.services.multi_recall import MultiRecallService
from app.routers.auth import get_session

router = APIRouter(prefix="/knowledge", tags=["知识库"])

# 全局 RAG 服务实例
_rag_service: Optional[RAGService] = None
_multi_recall_service: Optional[MultiRecallService] = None

# 构建任务状态
build_tasks = {}


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def get_multi_recall_service() -> MultiRecallService:
    """获取多路召回服务实例"""
    global _multi_recall_service
    if _multi_recall_service is None:
        _multi_recall_service = MultiRecallService()
    return _multi_recall_service


class BuildRequest(BaseModel):
    """知识库构建请求"""
    folder_ids: List[int]  # 要处理的收藏夹 ID 列表
    exclude_bvids: Optional[List[str]] = None  # 排除的视频
    include_bvids: Optional[List[str]] = None  # 只同步这些视频（优先级高于 exclude）


class BuildStatus(BaseModel):
    """构建状态"""
    task_id: str
    status: str  # pending / running / completed / failed
    progress: int  # 0-100
    current_step: str
    total_videos: int
    processed_videos: int
    message: str


class FolderStatus(BaseModel):
    """收藏夹入库状态"""
    media_id: int
    indexed_count: int
    media_count: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    # 详细统计（新增）
    stats: Optional[dict] = None  # {pending, processing, completed, failed, no_content}
    progress: Optional[int] = None  # 0-100


class VideoDetailStatus(BaseModel):
    """单个视频状态（含向量化状态）"""
    bvid: str
    title: str
    cover: Optional[str] = None
    owner: Optional[str] = None
    duration: Optional[int] = None
    processing_status: str  # pending/processing/completed/failed
    processing_step: Optional[str] = None
    processing_error: Optional[str] = None
    content_preview: Optional[str] = None
    asr_quality_score: Optional[float] = None
    created_at: Optional[datetime] = None


class FolderDetailStatus(BaseModel):
    """收藏夹详细状态（含视频列表）"""
    media_id: int
    stats: dict  # {pending, processing, completed, failed, no_content}
    videos: List[VideoDetailStatus]
    progress: int
    total: int
    page: int
    page_size: int
    has_more: bool


class RetryFailedRequest(BaseModel):
    """批量重试请求"""
    folder_ids: Optional[List[int]] = None
    bvids: Optional[List[str]] = None


class RetryFailedResponse(BaseModel):
    """批量重试响应"""
    task_id: str
    total: int
    message: str


class SyncRequest(BaseModel):
    """同步请求"""
    folder_ids: Optional[List[int]] = None


class SyncResult(BaseModel):
    """同步结果"""
    folder_id: int
    total: int
    added: int
    removed: int
    indexed: int
    message: str
    last_sync_at: Optional[datetime] = None


async def _get_or_create_folder(
    db: AsyncSession,
    session_id: str,
    media_id: int,
    title: Optional[str] = None,
    media_count: Optional[int] = None,
) -> FavoriteFolder:
    """获取或创建收藏夹记录"""
    result = await db.execute(
        select(FavoriteFolder).where(
            FavoriteFolder.session_id == session_id,
            FavoriteFolder.media_id == media_id,
        )
    )
    folder = result.scalar_one_or_none()

    if folder is None:
        folder = FavoriteFolder(
            session_id=session_id,
            media_id=media_id,
            title=title or "",
            media_count=media_count or 0,
            is_selected=True,
        )
        db.add(folder)
        await db.flush()
    else:
        if title:
            folder.title = title
        if media_count is not None:
            folder.media_count = media_count

    return folder


def _extract_video_info(media: dict) -> tuple[str, str, Optional[int]]:
    """抽取视频关键信息"""
    bvid = media.get("bvid") or media.get("bv_id")
    title = media.get("title", bvid)
    cid = None
    ugc = media.get("ugc") or {}
    if ugc.get("first_cid"):
        cid = ugc.get("first_cid")
    else:
        cid = media.get("cid") or media.get("id")
    return bvid, title, cid


async def _upsert_video_cache(db: AsyncSession, bvid: str, meta: dict) -> VideoCache:
    """写入或更新视频缓存信息，返回 VideoCache 对象"""
    result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
    cache = result.scalar_one_or_none()

    if cache is None:
        cache = VideoCache(
            bvid=bvid,
            title=meta.get("title") or bvid,
            description=meta.get("intro"),
            owner_name=meta.get("owner_name"),
            owner_mid=meta.get("owner_mid"),
            duration=meta.get("duration"),
            pic_url=meta.get("cover"),
            is_processed=False,
            processing_status="pending",
        )
        db.add(cache)
        await db.flush()
        return cache

    cache.title = meta.get("title") or cache.title
    if meta.get("intro") is not None:
        cache.description = meta.get("intro")
    if meta.get("owner_name") is not None:
        cache.owner_name = meta.get("owner_name")
    if meta.get("owner_mid") is not None:
        cache.owner_mid = meta.get("owner_mid")
    if meta.get("duration") is not None:
        cache.duration = meta.get("duration")

    await db.flush()
    return cache


async def _sync_folder(
    db: AsyncSession,
    bili: BilibiliService,
    rag: RAGService,
    content_fetcher: ContentFetcher,
    session_id: str,
    folder_id: int,
    exclude_bvids: Optional[set[str]] = None,
    include_bvids: Optional[set[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """同步单个收藏夹到向量库"""
    info = {}
    try:
        info_result = await bili.get_favorite_content(folder_id, pn=1, ps=1)
        info = info_result.get("info", {})
    except Exception as e:
        logger.warning(f"获取收藏夹信息失败 [{folder_id}]: {e}")

    videos = await bili.get_all_favorite_videos(folder_id)
    total_in_folder = info.get("media_count", len(videos))

    # 保护：接口异常返回空列表时，避免误删
    if not videos:
        if total_in_folder and total_in_folder > 0:
            logger.warning(f"[{folder_id}] 收藏夹返回空列表，跳过删除逻辑")
            existing_count = await db.scalar(
                select(func.count(FavoriteVideo.bvid))
                .where(FavoriteVideo.folder_id == folder_id)
            )
            return {
                "folder_id": folder_id,
                "total": total_in_folder,
                "added": 0,
                "removed": 0,
                "indexed": existing_count or 0,
                "message": "本次同步异常：空列表，已跳过",
                "last_sync_at": datetime.utcnow(),
            }

    video_map = {}
    skipped_invalid = 0
    semi_valid_medias = []

    for media in videos:
        bvid, title, cid = _extract_video_info(media)
        if not bvid:
            continue

        # 如果指定了 include_bvids，只处理这些视频
        if include_bvids and bvid not in include_bvids:
            continue

        if exclude_bvids and bvid in exclude_bvids:
            continue

        # 过滤失效视频
        attr = media.get("attr", 0)
        if attr == 9 or title in ["已失效视频", "已删除视频"]:
            skipped_invalid += 1
            logger.debug(f"跳过失效视频: {bvid} - {title}")
            continue

        semi_valid_medias.append(media)

    if skipped_invalid > 0:
        logger.info(f"[{folder_id}] 过滤了 {skipped_invalid} 个失效视频")

    # 并发获取多P展开
    import asyncio
    sem = asyncio.Semaphore(5)
    
    async def process_media(media):
        bvid, title, cid = _extract_video_info(media)
        owner = media.get("upper") or {}
        
        async with sem:
            try:
                pages = await bili.get_video_pagelist(bvid)
            except Exception as e:
                logger.warning(f"获取视频分P失败 [{bvid}]: {e}")
                pages = []
                
        parts_result = {}
        if pages and len(pages) > 1:
            for p in pages:
                page_num = p.get("page")
                part_title = p.get("part") or f"P{page_num}"
                full_title = f"[{page_num}/{len(pages)}] {title} - {part_title}"
                pseudo_bvid = f"{bvid}_p{page_num}"
                parts_result[pseudo_bvid] = {
                    "title": full_title,
                    "cid": p.get("cid"),
                    "intro": media.get("intro"),
                    "cover": media.get("cover"),
                    "duration": p.get("duration"),
                    "owner_name": owner.get("name"),
                    "owner_mid": owner.get("mid"),
                }
        else:
            parts_result[bvid] = {
                "title": title,
                "cid": cid,
                "intro": media.get("intro"),
                "cover": media.get("cover"),
                "duration": media.get("duration"),
                "owner_name": owner.get("name"),
                "owner_mid": owner.get("mid"),
            }
        return parts_result

    media_tasks = [process_media(m) for m in semi_valid_medias]
    all_parts_results = await asyncio.gather(*media_tasks) if media_tasks else []
    
    for p_res in all_parts_results:
        video_map.update(p_res)

    # 以有效视频数作为统计口径（包含展开后的长度）
    valid_count = len(video_map)
    current_bvids = set(video_map.keys())

    folder = await _get_or_create_folder(
        db,
        session_id=session_id,
        media_id=folder_id,
        title=info.get("title"),
        media_count=valid_count,
    )

    existing_rows = await db.execute(
        select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id == folder.id)
    )
    existing_bvids = {row[0] for row in existing_rows.fetchall()}

    added = current_bvids - existing_bvids
    removed = existing_bvids - current_bvids

    # 写入标题/简介等信息
    for bvid, meta in video_map.items():
        await _upsert_video_cache(db, bvid, meta)

    source_priority = {
        ContentSource.BASIC_INFO.value: 1,
        ContentSource.AI_SUMMARY.value: 2,
        ContentSource.SUBTITLE.value: 3,
        ContentSource.ASR.value: 4,
    }

    def _is_better_source(new_source: str, old_source: Optional[str]) -> bool:
        return source_priority.get(new_source, 0) > source_priority.get(old_source or "", 0)

    def _should_refresh_cache(cache: Optional[VideoCache]) -> bool:
        if not cache:
            return True
        text = (cache.content or "").strip()
        if len(text) < 50:
            return True
        if cache.content_source in (None, "", ContentSource.BASIC_INFO.value):
            return True
        return False

    def _is_asr_cache_usable(cache: Optional[VideoCache]) -> bool:
        if not cache:
            return False
        if cache.content_source != ContentSource.ASR.value:
            return False
        text = (cache.content or "").strip()
        return len(text) >= 50

    # 需要更新的已存在视频（缓存过少或来源较弱）
    update_candidates: set[str] = set()
    for bvid in current_bvids & existing_bvids:
        if bvid in added:
            continue
        result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
        cache = result.scalar_one_or_none()
        if _should_refresh_cache(cache):
            update_candidates.add(bvid)

    # 新增/更新向量与关联
    targets = list(added) + list(update_candidates)
    total_targets = len(targets)
    processed_targets = 0
    if progress_callback:
        progress_callback("准备处理", processed_targets, total_targets)

    for bvid in targets:
        meta = video_map[bvid]

        # 获取或创建 VideoCache
        cache = await _upsert_video_cache(db, bvid, meta)

        # 开始处理：设置处理状态
        cache.processing_status = "processing"
        cache.processing_step = "fetching"
        cache.processing_started_at = datetime.utcnow()
        cache.processing_completed_at = None
        cache.process_error = None

        # 尝试添加到向量库（可能失败，但不影响记录入库）
        try:
            global_count = await db.scalar(
                select(func.count()).select_from(FavoriteVideo).where(FavoriteVideo.bvid == bvid)
            )
            # 检查缓存内容是否缺失
            old_content = (cache.content or "").strip() if cache else ""
            old_source = cache.content_source if cache else None

            needs_fetch = _should_refresh_cache(cache)
            content = None
            should_update_cache = False
            should_reindex = False

            if needs_fetch:
                # 更新步骤为获取内容
                cache.processing_step = "fetching"
                content = await content_fetcher.fetch_content(
                    bvid, cid=meta["cid"], title=meta["title"]
                )
                new_text = (content.content or "").strip() if content else ""
                new_source = content.source.value if content else None

                if not old_content:
                    should_update_cache = True
                    should_reindex = True
                elif new_source and _is_better_source(new_source, old_source):
                    should_update_cache = True
                    should_reindex = True
                elif new_text and new_text != old_content:
                    should_update_cache = True
                    should_reindex = True

                if cache and should_update_cache:
                    cache.processing_step = "content_ready"
                    cache.content = content.content
                    cache.content_source = content.source.value
                    cache.outline_json = content.outline
                    cache.is_processed = True
                    # 保存 ASR 质量评估结果
                    if content.asr_quality_score is not None:
                        cache.asr_quality_score = content.asr_quality_score
                        # 写入质量评估日志
                        quality_log = ASRQualityLog(
                            bvid=bvid,
                            quality_score=content.asr_quality_score,
                            quality_flags=content.asr_quality_flags,
                            confidence_avg=content.confidence_avg,
                            confidence_min=content.confidence_min,
                            audio_duration=content.audio_duration,
                            audio_quality=content.audio_quality,
                            speech_ratio=content.speech_ratio,
                            asr_model=content.asr_model,
                            word_count=content.word_count,
                        )
                        db.add(quality_log)
                    if content.asr_quality_flags is not None:
                        cache.asr_quality_flags = content.asr_quality_flags
                    if content.asr_model:
                        cache.asr_model = content.asr_model
                    logger.info(f"[{bvid}] 已写入缓存: source={cache.content_source}")

            # 需要重建向量：新增/升级/内容变化 或 向量缺失
            if (global_count == 0) or should_reindex:
                if not content:
                    if _is_asr_cache_usable(cache):
                        content = VideoContent(
                            bvid=bvid,
                            title=meta["title"],
                            content=(cache.content or "").strip(),
                            source=ContentSource.ASR,
                            outline=cache.outline_json,
                            # 从缓存恢复质量评估字段
                            asr_quality_score=cache.asr_quality_score,
                            asr_quality_flags=cache.asr_quality_flags,
                            asr_model=cache.asr_model,
                        )
                        cache.is_processed = True
                        logger.info(f"[{bvid}] 使用缓存 ASR 内容重建向量")
                    else:
                        content = await content_fetcher.fetch_content(
                            bvid, cid=meta["cid"], title=meta["title"]
                        )
                        if cache:
                            cache.content = content.content
                            cache.content_source = content.source.value
                            cache.outline_json = content.outline
                            cache.is_processed = True
                            # 保存 ASR 质量评估结果
                            if content.asr_quality_score is not None:
                                cache.asr_quality_score = content.asr_quality_score
                                # 写入质量评估日志
                                quality_log = ASRQualityLog(
                                    bvid=bvid,
                                    quality_score=content.asr_quality_score,
                                    quality_flags=content.asr_quality_flags,
                                    confidence_avg=content.confidence_avg,
                                    confidence_min=content.confidence_min,
                                    audio_duration=content.audio_duration,
                                    audio_quality=content.audio_quality,
                                    speech_ratio=content.speech_ratio,
                                    asr_model=content.asr_model,
                                    word_count=content.word_count,
                                )
                                db.add(quality_log)
                            if content.asr_quality_flags is not None:
                                cache.asr_quality_flags = content.asr_quality_flags
                            if content.asr_model:
                                cache.asr_model = content.asr_model
                            logger.info(f"[{bvid}] 已写入缓存: source={cache.content_source}")
                try:
                    # 更新步骤为向量化
                    cache.processing_step = "embedding"
                    rag.delete_video(bvid)
                except Exception as e:
                    logger.warning(f"删除旧向量失败 [{bvid}]: {e}")
                chunks = rag.add_video_content(content)

                # 向量化成功：更新状态
                cache.processing_status = "completed"
                cache.processing_step = "completed"
                cache.processing_completed_at = datetime.utcnow()
                logger.info(f"[{bvid}] 向量化完成，块数={chunks}")
            else:
                # 内容未变化但向量已存在，标记为已完成
                if cache.is_processed:
                    cache.processing_status = "completed"
                    cache.processing_step = "completed"
                    cache.processing_completed_at = datetime.utcnow()
                logger.info(f"[{bvid}] 内容未变化或无需升级，跳过向量化")
        except Exception as e:
            # 处理失败：更新状态
            cache.processing_status = "failed"
            cache.processing_step = "failed"
            cache.process_error = str(e)
            logger.warning(f"添加向量失败 [{bvid}]: {e} (仍会记录到数据库)")
        
        # 无论向量是否添加成功，都写入 FavoriteVideo 记录
        try:
            exists_row = await db.execute(
                select(FavoriteVideo.id).where(
                    FavoriteVideo.folder_id == folder.id,
                    FavoriteVideo.bvid == bvid,
                )
            )
            if exists_row.scalar_one_or_none() is None:
                db.add(FavoriteVideo(folder_id=folder.id, bvid=bvid, is_selected=True))
            processed_targets += 1
            if progress_callback:
                progress_callback(meta["title"], processed_targets, total_targets)
        except Exception as e:
            logger.error(f"写入数据库失败 [{bvid}]: {e}")

    # 删除无效向量
    if removed:
        for bvid in removed:
            other_count = await db.scalar(
                select(func.count())
                .select_from(FavoriteVideo)
                .where(
                    FavoriteVideo.bvid == bvid,
                    FavoriteVideo.folder_id != folder.id,
                )
            )
            if other_count == 0:
                try:
                    rag.delete_video(bvid)
                except Exception as e:
                    logger.warning(f"删除向量失败 [{bvid}]: {e}")

        await db.execute(
            delete(FavoriteVideo).where(
                FavoriteVideo.folder_id == folder.id,
                FavoriteVideo.bvid.in_(removed),
            )
        )

    folder.last_sync_at = datetime.utcnow()

    await db.commit()

    indexed_count = await db.scalar(
        select(func.count(func.distinct(FavoriteVideo.bvid)))
        .select_from(FavoriteVideo)
        .where(FavoriteVideo.folder_id == folder.id)
    )

    return {
        "folder_id": folder_id,
        "total": valid_count,
        "added": len(added),
        "removed": len(removed),
        "indexed": indexed_count or 0,
        "message": "同步完成",
        "last_sync_at": folder.last_sync_at,
    }


@router.get("/stats")
async def get_knowledge_stats():
    """获取知识库统计信息"""
    try:
        rag = get_rag_service()
        stats = rag.get_collection_stats()
        return stats
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 先定义更具体的路由（带路径参数的）
logger.info("=== get_folder_detail_status route called ===")

@router.get("/folders/{media_id}/status", response_model=FolderDetailStatus)
async def get_folder_detail_status(
    media_id: int,
    session_id: str = Query(..., description="会话ID"),
    status_filter: Optional[str] = Query(None, description="筛选: pending/processing/completed/failed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取收藏夹详细状态（含视频列表、分页、筛选）"""
    logger.info(f"get_folder_detail_status called: media_id={media_id}, session_id={session_id}")
    # 1. 获取用户的 session_ids
    session = await get_session(session_id)
    if not session:
        logger.info(f"Session not found for session_id={session_id}")
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    mid = session.get("user_info", {}).get("mid") or session.get("cookies", {}).get("DedeUserID")

    target_session_ids = [session_id]
    if mid:
        result = await db.execute(
            select(UserSession.session_id).where(UserSession.bili_mid == mid)
        )
        target_session_ids = [row[0] for row in result.fetchall()]

    # 2. 查找收藏夹
    folder_result = await db.execute(
        select(FavoriteFolder).where(
            FavoriteFolder.media_id == media_id,
            FavoriteFolder.session_id.in_(target_session_ids)
        )
    )
    folder = folder_result.scalars().first()
    logger.info(f"Folder query: media_id={media_id}, target_session_ids={target_session_ids}, folder={folder}")
    if not folder:
        # 收藏夹未向量化，返回友好响应
        logger.info(f"Folder not found, returning empty status for media_id={media_id}")
        return FolderDetailStatus(
            media_id=media_id,
            stats={
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "no_content": 0
            },
            videos=[],
            progress=0,
            total=0,
            page=1,
            page_size=page_size,
            has_more=False
        )

    # 3. 获取该收藏夹下的所有视频
    video_result = await db.execute(
        select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id == folder.id)
    )
    all_bvids = [row[0] for row in video_result.fetchall()]

    # 4. 获取视频缓存信息
    cache_map = {}
    if all_bvids:
        cache_result = await db.execute(
            select(VideoCache).where(VideoCache.bvid.in_(all_bvids))
        )
        cache_map = {c.bvid: c for c in cache_result.scalars().all()}

    # 5. 构建视频状态列表
    video_details: List[VideoDetailStatus] = []
    pending_count = 0
    processing_count = 0
    completed_count = 0
    failed_count = 0
    no_content_count = 0

    # 6. 筛选状态
    for bvid in all_bvids:
        cache = cache_map.get(bvid)
        if cache:
            status = cache.processing_status or "pending"
            if status_filter and status != status_filter:
                continue

            if status == "pending":
                pending_count += 1
            elif status == "processing":
                processing_count += 1
            elif status == "completed":
                completed_count += 1
            elif status == "failed":
                failed_count += 1
            else:
                no_content_count += 1

            # 内容预览
            content = cache.content or cache.corrected_content or ""
            preview = content[:200] if content else None

            video_details.append(VideoDetailStatus(
                bvid=bvid,
                title=cache.title or bvid,
                cover=cache.pic_url,
                owner=cache.owner_name,
                duration=cache.duration,
                processing_status=status,
                processing_step=cache.processing_step,
                processing_error=cache.process_error,
                content_preview=preview,
                asr_quality_score=cache.asr_quality_score,
                created_at=cache.created_at,
            ))
        else:
            # 没有缓存记录，视为 pending
            if not status_filter or status_filter == "pending":
                pending_count += 1
                video_details.append(VideoDetailStatus(
                    bvid=bvid,
                    title=bvid,
                    processing_status="pending",
                ))

    # 7. 计算统计
    stats = {
        "pending": pending_count,
        "processing": processing_count,
        "completed": completed_count,
        "failed": failed_count,
        "no_content": no_content_count,
    }

    # 8. 分页
    total = len(video_details)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_videos = video_details[start:end]

    # 9. 计算进度
    total_videos = len(all_bvids)
    progress = int((completed_count / total_videos * 100)) if total_videos > 0 else 0

    return FolderDetailStatus(
        media_id=media_id,
        stats=stats,
        videos=paginated_videos,
        progress=progress,
        total=total_videos,
        page=page,
        page_size=page_size,
        has_more=end < total,
    )


@router.get("/video/{bvid}/detail", response_model=VideoDetailStatus)
async def get_video_detail(
    bvid: str,
    db: AsyncSession = Depends(get_db),
):
    """获取视频详情（含处理状态和错误信息）"""
    result = await db.execute(
        select(VideoCache).where(VideoCache.bvid == bvid)
    )
    cache = result.first()

    if not cache:
        raise HTTPException(status_code=404, detail="视频不存在")

    content = cache.content or cache.corrected_content or ""
    preview = content[:200] if content else None

    return VideoDetailStatus(
        bvid=bvid,
        title=cache.title or bvid,
        cover=cache.pic_url,
        owner=cache.owner_name,
        duration=cache.duration,
        processing_status=cache.processing_status or "pending",
        processing_step=cache.processing_step,
        processing_error=cache.process_error,
        content_preview=preview,
        asr_quality_score=cache.asr_quality_score,
        created_at=cache.created_at,
    )


@router.get("/folders/status", response_model=List[FolderStatus])
async def get_folder_status(
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取收藏夹入库状态（跨 Session 查找同一用户的数据）"""

    # 1. 先查当前 Session 对应的用户 MID
    result = await db.execute(
        select(UserSession.bili_mid).where(UserSession.session_id == session_id)
    )
    mid = result.scalar()

    target_session_ids = [session_id]

    if mid:
        # 2. 如果有 MID，查找该用户所有的 Session ID
        result = await db.execute(
            select(UserSession.session_id).where(UserSession.bili_mid == mid)
        )
        target_session_ids = [row[0] for row in result.fetchall()]

    # 3. 查询所有关联 Session 的收藏夹状态
    rows = await db.execute(
        select(FavoriteFolder.id, FavoriteFolder.media_id, FavoriteFolder.last_sync_at)
        .where(FavoriteFolder.session_id.in_(target_session_ids))
        .order_by(FavoriteFolder.updated_at.desc())
    )

    # 手动按 media_id 去重，保留最新的
    folders_map = {}
    for row in rows.fetchall():
        fid, media_id, last_sync = row
        if media_id not in folders_map:
            folders_map[media_id] = (fid, last_sync)

    if not folders_map:
        return []

    folder_ids = [v[0] for v in folders_map.values()]

    # 4. 统计视频数量
    counts = await db.execute(
        select(FavoriteVideo.folder_id, func.count(func.distinct(FavoriteVideo.bvid)))
        .where(FavoriteVideo.folder_id.in_(folder_ids))
        .group_by(FavoriteVideo.folder_id)
    )
    count_map = {row[0]: row[1] for row in counts.fetchall()}

    result = []
    for media_id, (folder_id, last_sync_at) in folders_map.items():
        # 读取有效视频数
        folder_row = await db.execute(
            select(FavoriteFolder.media_count).where(FavoriteFolder.id == folder_id)
        )
        media_count = folder_row.scalar()

        # 查询视频处理状态统计
        processing_counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0, "no_content": 0}
        video_bvids_result = await db.execute(
            select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id == folder_id)
        )
        bvids = [row[0] for row in video_bvids_result.fetchall()]

        if bvids:
            status_result = await db.execute(
                select(VideoCache.processing_status, func.count())
                .where(VideoCache.bvid.in_(bvids))
                .group_by(VideoCache.processing_status)
            )
            for status, cnt in status_result.fetchall():
                if status in processing_counts:
                    processing_counts[status] = cnt
                else:
                    processing_counts["no_content"] += cnt

            total_statused = sum(processing_counts.values())
            if total_statused < len(bvids):
                processing_counts["pending"] = len(bvids) - total_statused

        total_videos = len(bvids) if bvids else 0
        completed = processing_counts.get("completed", 0)
        progress = int((completed / total_videos) * 100) if total_videos > 0 else 0

        result.append(
            FolderStatus(
                media_id=media_id,
                indexed_count=count_map.get(folder_id, 0),
                media_count=media_count,
                last_sync_at=last_sync_at,
                stats=processing_counts,
                progress=progress,
            )
        )
    return result


@router.post("/retry-failed", response_model=RetryFailedResponse)
async def retry_failed_videos(
    request: RetryFailedRequest,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """批量重新处理失败/待处理的视频"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})
    user_info = session.get("user_info", {})

    bvids_to_retry: List[str] = []

    if request.bvids:
        # 1. 指定了特定视频
        bvids_to_retry = request.bvids
    elif request.folder_ids:
        # 2. 指定了收藏夹，查找该收藏夹下失败/待处理的视频
        mid = user_info.get("mid") or cookies.get("DedeUserID")
        target_session_ids = [session_id]
        if mid:
            result = await db.execute(
                select(UserSession.session_id).where(UserSession.bili_mid == mid)
            )
            target_session_ids = [row[0] for row in result.fetchall()]

        for folder_id in request.folder_ids:
            folder_result = await db.execute(
                select(FavoriteFolder.id).where(
                    FavoriteFolder.media_id == folder_id,
                    FavoriteFolder.session_id.in_(target_session_ids)
                )
            )
            folder_db_id = folder_result.scalar()

            if folder_db_id:
                video_result = await db.execute(
                    select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id == folder_db_id)
                )
                folder_bvids = [row[0] for row in video_result.fetchall()]

                # 查找失败/待处理的视频
                cache_result = await db.execute(
                    select(VideoCache.bvid).where(
                        VideoCache.bvid.in_(folder_bvids),
                        VideoCache.processing_status.in_(["failed", "pending", "no_content"])
                    )
                )
                bvids_to_retry.extend(cache_result.scalars().all())

    if not bvids_to_retry:
        return RetryFailedResponse(
            task_id="",
            total=0,
            message="没有需要重试的视频"
        )

    # 3. 异步重新处理视频
    import uuid
    task_id = str(uuid.uuid4())

    # 直接更新状态为 pending，等待下次 sync 时处理
    await db.execute(
        update(VideoCache)
        .where(VideoCache.bvid.in_(bvids_to_retry))
        .values(processing_status="pending", process_error=None)
    )
    await db.commit()

    return RetryFailedResponse(
        task_id=task_id,
        total=len(bvids_to_retry),
        message=f"已标记 {len(bvids_to_retry)} 个视频待重新处理"
    )


@router.post("/folders/sync", response_model=List[SyncResult])
async def sync_folders(
    request: SyncRequest,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """同步收藏夹到向量库"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})
    user_info = session.get("user_info", {})

    bili = BilibiliService(
        sessdata=cookies.get("SESSDATA"),
        bili_jct=cookies.get("bili_jct"),
        dedeuserid=cookies.get("DedeUserID"),
    )
    rag = get_rag_service()
    asr_service = ASRService()
    content_fetcher = ContentFetcher(bili, asr_service)

    try:
        folder_ids = request.folder_ids or []
        if not folder_ids:
            mid = user_info.get("mid") or cookies.get("DedeUserID")
            if not mid:
                raise HTTPException(status_code=400, detail="无法获取用户信息")
            folders = await bili.get_user_favorites(mid=mid)
            folder_ids = [folder.get("id") for folder in folders if folder.get("id")]

        results: List[SyncResult] = []
        for folder_id in folder_ids:
            try:
                result = await _sync_folder(
                    db,
                    bili,
                    rag,
                    content_fetcher,
                    session_id,
                    folder_id,
                )
                results.append(SyncResult(**result))
            except Exception as e:
                logger.error(f"同步收藏夹失败 [{folder_id}]: {e}")
                results.append(
                    SyncResult(
                        folder_id=folder_id,
                        total=0,
                        added=0,
                        removed=0,
                        indexed=0,
                        message=f"同步失败: {e}",
                        last_sync_at=None,
                    )
                )

        return results
    finally:
        await bili.close()


@router.post("/build")
async def build_knowledge_base(
    request: BuildRequest,
    background_tasks: BackgroundTasks,
    session_id: str = Query(..., description="会话ID"),
):
    """构建知识库（后台任务）"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    import uuid
    task_id = str(uuid.uuid4())

    build_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "current_step": "初始化中...",
        "total_videos": 0,
        "processed_videos": 0,
        "message": "",
    }

    background_tasks.add_task(
        _build_knowledge_base_task,
        task_id,
        session_id,
        session,
        request.folder_ids,
        request.exclude_bvids or [],
        request.include_bvids or [],
    )

    return {"task_id": task_id, "message": "构建任务已启动"}


async def _build_knowledge_base_task(
    task_id: str,
    session_id: str,
    session: dict,
    folder_ids: List[int],
    exclude_bvids: List[str],
    include_bvids: List[str] = None,
):
    """后台构建任务"""
    cookies = session.get("cookies", {})

    try:
        build_tasks[task_id]["status"] = "running"
        build_tasks[task_id]["current_step"] = "同步收藏夹..."

        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID"),
        )
        asr_service = ASRService()
        content_fetcher = ContentFetcher(bili, asr_service)
        rag = get_rag_service()

        try:
            total_folders = len(folder_ids)
            if total_folders == 0:
                build_tasks[task_id]["status"] = "completed"
                build_tasks[task_id]["progress"] = 100
                build_tasks[task_id]["message"] = "没有需要处理的收藏夹"
                return

            processed = 0
            total_added = 0
            total_removed = 0

            async with get_db_context() as db:
                for idx, folder_id in enumerate(folder_ids, start=1):
                    build_tasks[task_id]["current_step"] = f"同步收藏夹 {folder_id}"

                    def progress_cb(title: str, processed_count: int = 0, total_count: int = 0):
                        build_tasks[task_id]["current_step"] = f"处理: {title}"
                        if total_count:
                            build_tasks[task_id]["total_videos"] = total_count
                        if processed_count:
                            build_tasks[task_id]["processed_videos"] = processed_count
                            if build_tasks[task_id]["total_videos"]:
                                build_tasks[task_id]["progress"] = int(
                                    (processed_count / build_tasks[task_id]["total_videos"]) * 100
                                )

                    result = await _sync_folder(
                        db,
                        bili,
                        rag,
                        content_fetcher,
                        session_id,
                        folder_id,
                        exclude_bvids=set(exclude_bvids) if exclude_bvids else None,
                        include_bvids=set(include_bvids) if include_bvids else None,
                        progress_callback=progress_cb,
                    )

                    processed = idx
                    total_added += result["added"]
                    total_removed += result["removed"]

            build_tasks[task_id]["status"] = "completed"
            build_tasks[task_id]["progress"] = 100
            build_tasks[task_id]["processed_videos"] = total_folders
            build_tasks[task_id]["current_step"] = "完成"
            build_tasks[task_id]["message"] = f"同步完成：新增 {total_added}，移除 {total_removed}"

            logger.info(f"知识库构建完成: 新增 {total_added}，移除 {total_removed}")
        finally:
            await bili.close()

    except Exception as e:
        logger.error(f"构建任务失败: {e}")
        build_tasks[task_id]["status"] = "failed"
        build_tasks[task_id]["message"] = str(e)


@router.get("/build/status/{task_id}", response_model=BuildStatus)
async def get_build_status(task_id: str):
    """获取构建任务状态"""
    if task_id not in build_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = build_tasks[task_id]
    return BuildStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        current_step=task["current_step"],
        total_videos=task["total_videos"],
        processed_videos=task["processed_videos"],
        message=task["message"],
    )


@router.delete("/clear")
async def clear_knowledge_base():
    """清空知识库"""
    try:
        rag = get_rag_service()
        rag.clear_collection()
        return {"message": "知识库已清空"}
    except Exception as e:
        logger.error(f"清空知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/video/{bvid}")
async def delete_video_from_knowledge(bvid: str):
    """从知识库中删除指定视频"""
    try:
        rag = get_rag_service()
        rag.delete_video(bvid)
        return {"message": f"已删除视频 {bvid}"}
    except Exception as e:
        logger.error(f"删除视频失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== ASR 状态与纠错 API ==============

class ASRStatusResponse(BaseModel):
    """ASR 状态响应"""
    bvid: str
    asr_status: str  # pending / processing / completed / failed
    asr_model: Optional[str] = None
    asr_duration: Optional[int] = None
    asr_quality_score: Optional[float] = None
    asr_quality_flags: Optional[List[str]] = None
    content: Optional[str] = None
    is_corrected: bool = False


class ASRQualityResponse(BaseModel):
    """ASR 质量报告响应"""
    bvid: str
    asr_model: Optional[str] = None
    audio_duration: Optional[int] = None
    quality_score: Optional[float] = None
    quality_flags: Optional[List[str]] = None
    confidence_avg: Optional[float] = None
    confidence_min: Optional[float] = None
    audio_quality: Optional[str] = None
    speech_ratio: Optional[float] = None
    word_count: Optional[int] = None
    processed_at: Optional[datetime] = None


@router.get("/video/{bvid}/asr-status", response_model=ASRStatusResponse)
async def get_asr_status(
    bvid: str,
    db: AsyncSession = Depends(get_db),
):
    """获取视频 ASR 状态"""
    result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
    cache = result.scalar_one_or_none()

    if not cache:
        # 视频未向量化，返回友好响应
        return ASRStatusResponse(
            bvid=bvid,
            asr_status="not_indexed",
            asr_model=None,
            asr_duration=None,
            asr_quality_score=None,
            asr_quality_flags=[],
            content=None,
            is_corrected=False,
            corrected_content=None,
            created_at=None
        )

    # 根据内容来源和处理状态确定 ASR 状态
    asr_status = "pending"
    if cache.content_source == "asr":
        if cache.content and len(cache.content.strip()) >= 50:
            asr_status = "completed"
        elif cache.process_error:
            asr_status = "failed"
        else:
            asr_status = "processing"
    elif cache.process_error:
        asr_status = "failed"

    # 返回 ASR 内容（优先返回校正后的内容）
    content = None
    if cache.is_corrected and cache.corrected_content:
        content = cache.corrected_content
    elif cache.content_source == "asr":
        content = cache.content

    return ASRStatusResponse(
        bvid=bvid,
        asr_status=asr_status,
        asr_model=cache.asr_model,
        asr_duration=cache.asr_duration,
        asr_quality_score=cache.asr_quality_score,
        asr_quality_flags=cache.asr_quality_flags,
        content=content,
        is_corrected=cache.is_corrected or False,
    )


class ASRCorrectRequest(BaseModel):
    """ASR 纠错请求"""
    corrected_content: str


@router.get("/video/{bvid}/asr-quality", response_model=ASRQualityResponse)
async def get_asr_quality(
    bvid: str,
    db: AsyncSession = Depends(get_db),
):
    """获取视频 ASR 质量报告"""
    result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
    cache = result.scalar_one_or_none()

    if not cache:
        raise HTTPException(status_code=404, detail=f"视频 {bvid} 不存在")

    if cache.content_source != "asr" or not cache.asr_model:
        raise HTTPException(status_code=400, detail="该视频未进行 ASR 处理")

    # 尝试从 ASRQualityLog 获取更详细的质量信息
    quality_result = await db.execute(
        select(ASRQualityLog)
        .where(ASRQualityLog.bvid == bvid)
        .order_by(ASRQualityLog.created_at.desc())
        .limit(1)
    )
    quality_log = quality_result.scalar_one_or_none()

    return ASRQualityResponse(
        bvid=bvid,
        asr_model=cache.asr_model,
        audio_duration=cache.asr_duration,
        quality_score=cache.asr_quality_score,
        quality_flags=cache.asr_quality_flags,
        confidence_avg=quality_log.confidence_avg if quality_log else None,
        confidence_min=quality_log.confidence_min if quality_log else None,
        audio_quality=quality_log.audio_quality if quality_log else None,
        speech_ratio=quality_log.speech_ratio if quality_log else None,
        word_count=quality_log.word_count if quality_log else None,
        processed_at=quality_log.created_at if quality_log else None,
    )


@router.post("/video/{bvid}/asr-correct", response_model=ASRStatusResponse)
async def correct_asr(
    bvid: str,
    request: ASRCorrectRequest,
    db: AsyncSession = Depends(get_db),
):
    """校正 ASR 内容"""
    result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
    cache = result.scalar_one_or_none()

    if not cache:
        raise HTTPException(status_code=404, detail=f"视频 {bvid} 不存在")

    if cache.content_source != "asr":
        raise HTTPException(status_code=400, detail="该视频未使用 ASR 内容，无法校正")

    # 更新校正内容
    cache.corrected_content = request.corrected_content
    cache.is_corrected = True
    cache.corrected_at = datetime.utcnow()
    cache.corrected_by = "user"

    await db.commit()

    # 重新索引到向量库
    try:
        rag = get_rag_service()
        # 删除旧向量
        rag.delete_video(bvid)
        # 添加新内容
        from app.models import ContentSource
        from app.services.content_fetcher import VideoContent
        content = VideoContent(
            bvid=bvid,
            title=cache.title,
            content=request.corrected_content,
            source=ContentSource.ASR,
            asr_quality_score=cache.asr_quality_score,
            asr_quality_flags=cache.asr_quality_flags,
            asr_model=cache.asr_model,
        )
        rag.add_video_content(content)
        logger.info(f"[{bvid}] 校正后已重新索引向量库")
    except Exception as e:
        logger.warning(f"[{bvid}] 重新索引向量库失败: {e}")

    return ASRStatusResponse(
        bvid=bvid,
        asr_status="completed",
        asr_model=cache.asr_model,
        asr_duration=cache.asr_duration,
        asr_quality_score=cache.asr_quality_score,
        asr_quality_flags=cache.asr_quality_flags,
        content=request.corrected_content,
        is_corrected=True,
    )
