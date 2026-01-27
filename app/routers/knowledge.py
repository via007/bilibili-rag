"""
Bilibili RAG 知识库系统

知识库路由 - 构建和管理知识库
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional, Callable
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_context
from app.models import FavoriteFolder, FavoriteVideo, VideoCache, UserSession, ContentSource, VideoContent
from app.services.bilibili import BilibiliService
from app.services.content_fetcher import ContentFetcher
from app.services.asr import ASRService
from app.services.rag import RAGService
from app.routers.auth import get_session

router = APIRouter(prefix="/knowledge", tags=["知识库"])

# 全局 RAG 服务实例
_rag_service: Optional[RAGService] = None

# 构建任务状态
build_tasks = {}


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


class BuildRequest(BaseModel):
    """知识库构建请求"""
    folder_ids: List[int]  # 要处理的收藏夹 ID 列表
    exclude_bvids: Optional[List[str]] = None  # 排除的视频


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


async def _upsert_video_cache(db: AsyncSession, bvid: str, meta: dict) -> None:
    """写入或更新视频缓存信息"""
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
        )
        db.add(cache)
        return

    cache.title = meta.get("title") or cache.title
    if meta.get("intro") is not None:
        cache.description = meta.get("intro")
    if meta.get("owner_name") is not None:
        cache.owner_name = meta.get("owner_name")
    if meta.get("owner_mid") is not None:
        cache.owner_mid = meta.get("owner_mid")
    if meta.get("duration") is not None:
        cache.duration = meta.get("duration")
    if meta.get("cover") is not None:
        cache.pic_url = meta.get("cover")


async def _sync_folder(
    db: AsyncSession,
    bili: BilibiliService,
    rag: RAGService,
    content_fetcher: ContentFetcher,
    session_id: str,
    folder_id: int,
    exclude_bvids: Optional[set[str]] = None,
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
    for media in videos:
        bvid, title, cid = _extract_video_info(media)
        if not bvid:
            continue
        if exclude_bvids and bvid in exclude_bvids:
            continue
        
        # 过滤失效视频（被删除、下架等）
        # attr 字段: 0=正常, 9=已失效, 1=私密等
        attr = media.get("attr", 0)
        if attr == 9 or title in ["已失效视频", "已删除视频"]:
            skipped_invalid += 1
            logger.debug(f"跳过失效视频: {bvid} - {title}")
            continue
        
        owner = media.get("upper") or {}
        video_map[bvid] = {
            "title": title,
            "cid": cid,
            "intro": media.get("intro"),
            "cover": media.get("cover"),
            "duration": media.get("duration"),
            "owner_name": owner.get("name"),
            "owner_mid": owner.get("mid"),
        }
    
    if skipped_invalid > 0:
        logger.info(f"[{folder_id}] 过滤了 {skipped_invalid} 个失效视频")

    # 以有效视频数作为统计口径（过滤失效视频）
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
        
        # 尝试添加到向量库（可能失败，但不影响记录入库）
        try:
            global_count = await db.scalar(
                select(func.count()).select_from(FavoriteVideo).where(FavoriteVideo.bvid == bvid)
            )
            # 检查缓存内容是否缺失
            result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
            cache = result.scalar_one_or_none()
            old_content = (cache.content or "").strip() if cache else ""
            old_source = cache.content_source if cache else None

            needs_fetch = _should_refresh_cache(cache)
            content = None
            should_update_cache = False
            should_reindex = False

            if needs_fetch:
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
                    cache.content = content.content
                    cache.content_source = content.source.value
                    cache.outline_json = content.outline
                    cache.is_processed = True
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
                            logger.info(f"[{bvid}] 已写入缓存: source={cache.content_source}")
                try:
                    rag.delete_video(bvid)
                except Exception as e:
                    logger.warning(f"删除旧向量失败 [{bvid}]: {e}")
                chunks = rag.add_video_content(content)
                logger.info(f"[{bvid}] 向量化完成，块数={chunks}")
            else:
                logger.info(f"[{bvid}] 内容未变化或无需升级，跳过向量化")
        except Exception as e:
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
    # 使用 group_by media_id 来去重，取最新的那个
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
        # 读取有效视频数（过滤失效后的口径）
        folder_row = await db.execute(
            select(FavoriteFolder.media_count).where(FavoriteFolder.id == folder_id)
        )
        media_count = folder_row.scalar()
        result.append(
            FolderStatus(
                media_id=media_id,
                indexed_count=count_map.get(folder_id, 0),
                media_count=media_count,
                last_sync_at=last_sync_at,
            )
        )
    return result


@router.post("/folders/sync", response_model=List[SyncResult])
async def sync_folders(
    request: SyncRequest,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """同步收藏夹到向量库"""
    session = get_session(session_id)
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
    session = get_session(session_id)
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
    )

    return {"task_id": task_id, "message": "构建任务已启动"}


async def _build_knowledge_base_task(
    task_id: str,
    session_id: str,
    session: dict,
    folder_ids: List[int],
    exclude_bvids: List[str],
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
                        exclude_bvids=set(exclude_bvids),
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
