"""
Bilibili RAG 知识库系统

收藏夹路由
"""
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel
from app.models import FavoriteFolderInfo
from app.services.bilibili import BilibiliService
from app.routers.auth import get_session

router = APIRouter(prefix="/favorites", tags=["收藏夹"])


def _is_default_folder(folder: dict) -> bool:
    for key in ("is_default", "default", "isDefault"):
        if key in folder:
            return bool(folder.get(key))
    if folder.get("type") == 1:
        return True
    if folder.get("fav_state") == 1:
        return True
    if folder.get("attr") == 1:
        return True
    title = (folder.get("title") or "").strip()
    return title == "默认收藏夹"


class OrganizePreviewRequest(BaseModel):
    folder_id: int


class OrganizePreviewItem(BaseModel):
    bvid: str
    title: str
    resource_id: int
    resource_type: int
    target_folder_id: Optional[int] = None
    target_folder_title: str
    reason: Optional[str] = None


class OrganizePreviewResponse(BaseModel):
    default_folder_id: int
    default_folder_title: str
    folders: List[FavoriteFolderInfo]
    items: List[OrganizePreviewItem]
    stats: dict


class OrganizeMoveItem(BaseModel):
    resource_id: int
    resource_type: int
    target_folder_id: int


class OrganizeExecuteRequest(BaseModel):
    default_folder_id: int
    moves: List[OrganizeMoveItem]


class CleanInvalidRequest(BaseModel):
    folder_id: int


@router.get("/video/{bvid}/parts")
async def get_video_parts(
    bvid: str,
    session_id: str = Query(..., description="会话ID")
):
    """
    获取视频的分P列表（用于点击展开时显示该视频的所有分P）
    """
    logger.info(f"[get_video_parts] 收到请求: bvid={bvid}, session_id={session_id[:20] if session_id else 'None'}...")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})

    # 去掉可能的 _p 后缀，获取原始 bvid
    original_bvid = bvid.split("_p")[0]

    try:
        logger.info(f"获取视频分P列表: bvid={original_bvid}")
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )

        # 获取分P列表
        pages = await bili.get_video_pagelist(original_bvid)

        # 获取视频基本信息
        video_info = await bili.get_video_info(original_bvid)

        await bili.close()

        # 构建分P数据
        parts = []
        if pages and len(pages) > 1:
            for p in pages:
                page_num = p.get("page")
                part_title = p.get("part") or f"P{page_num}"
                # 只保留核心部分（减号后面的内容）
                core_title = part_title
                if " - " in part_title:
                    core_title = part_title.split(" - ")[-1].strip()
                parts.append({
                    "bvid": f"{original_bvid}_p{page_num}",
                    "title": f"[{page_num}/{len(pages)}] {core_title}",
                    "full_title": f"[{page_num}/{len(pages)}] {video_info.get('title', '')} - {part_title}",
                    "page": page_num,
                    "cid": p.get("cid"),
                    "duration": p.get("duration")
                })
        else:
            # 只有一个P的情况
            parts.append({
                "bvid": original_bvid,
                "title": video_info.get("title", ""),
                "page": 1,
                "cid": pages[0].get("cid") if pages else None,
                "duration": pages[0].get("duration") if pages else None
            })

        return {
            "bvid": original_bvid,
            "title": video_info.get("title", ""),
            "cover": video_info.get("cover", ""),
            "owner": video_info.get("owner", {}).get("name") if isinstance(video_info.get("owner"), dict) else video_info.get("owner", ""),
            "parts": parts,
            "total_parts": len(parts)
        }

    except Exception as e:
        logger.error(f"获取视频分P失败: {e}")
        if 'bili' in locals():
            await bili.close()
        raise HTTPException(status_code=500, detail=f"获取视频分P失败: {str(e)}")


@router.get("/series/{bvid}/videos")
async def get_series_videos_by_bvid(
    bvid: str,
    session_id: str = Query(..., description="会话ID")
):
    """
    根据bvid获取视频的分P列表或系列视频
    用于点击展开按钮时显示视频列表
    1. 先获取视频的分P列表
    2. 如果有多个分P，返回分P列表
    3. 如果没有分P，尝试获取系列视频
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})
    original_bvid = bvid.split("_p")[0]

    try:
        logger.info(f"获取视频信息: bvid={original_bvid}")
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )

        # 获取视频基本信息
        video_info = await bili.get_video_info(original_bvid)
        video_title = video_info.get("title", "")
        video_cover = video_info.get("cover", "")
        video_owner = video_info.get("upper", {}).get("name") if isinstance(video_info.get("upper"), dict) else ""

        logger.info(f"视频标题: {video_title}")

        # 首先获取视频的分P列表
        pages = await bili.get_video_pagelist(original_bvid)
        logger.info(f"分P数量: {len(pages)}")

        videos = []

        # 如果有多个分P，返回分P列表
        if pages and len(pages) > 1:
            logger.info(f"返回分P列表，共 {len(pages)} 个P")
            for p in pages:
                page_num = p.get("page")
                part_title = p.get("part") or f"P{page_num}"
                videos.append({
                    "bvid": f"{original_bvid}_p{page_num}",
                    "title": f"[{page_num}/{len(pages)}] {part_title}",
                    "cover": video_cover,
                    "duration": p.get("duration"),
                    "owner": video_owner,
                    "original_bvid": original_bvid,
                    "page": page_num,
                    "cid": p.get("cid"),
                    "is_part": True
                })
        elif pages and len(pages) == 1:
            # 只有一个P，返回基本信息
            videos.append({
                "bvid": original_bvid,
                "title": video_title,
                "cover": video_cover,
                "duration": pages[0].get("duration"),
                "owner": video_owner,
                "original_bvid": original_bvid,
                "is_part": False
            })
        else:
            # 没有分P信息，返回基本信息
            videos.append({
                "bvid": original_bvid,
                "title": video_title,
                "cover": video_cover,
                "duration": video_info.get("duration"),
                "owner": video_owner,
                "original_bvid": original_bvid,
                "is_part": False
            })

        await bili.close()

        return {
            "total": len(videos),
            "videos": videos
        }

    except Exception as e:
        logger.error(f"获取视频列表失败: {e}")
        if 'bili' in locals():
            await bili.close()
        raise HTTPException(status_code=500, detail=f"获取视频列表失败: {str(e)}")
        if 'bili' in locals():
            await bili.close()
        raise HTTPException(status_code=500, detail=f"获取系列视频失败: {str(e)}")


@router.get("/list", response_model=List[FavoriteFolderInfo])
async def get_favorites_list(session_id: str = Query(..., description="会话ID")):
    """
    获取用户的收藏夹列表
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    
    cookies = session.get("cookies", {})
    user_info = session.get("user_info", {})
    
    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )
        
        mid = user_info.get("mid") or cookies.get("DedeUserID")
        folders = await bili.get_user_favorites(mid=mid)
        await bili.close()
        
        result = []
        for folder in folders:
            result.append(FavoriteFolderInfo(
                media_id=folder["id"],
                title=folder["title"],
                media_count=folder.get("media_count", 0),
                is_selected=True,
                is_default=_is_default_folder(folder)
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"获取收藏夹列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取收藏夹失败: {str(e)}")


@router.get("/{media_id}/videos")
async def get_favorite_videos(
    media_id: int,
    session_id: str = Query(..., description="会话ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=20)
):
    """
    获取收藏夹中的视频列表
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    
    cookies = session.get("cookies", {})
    
    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )
        
        result = await bili.get_favorite_content(media_id, pn=page, ps=page_size)

        import asyncio

        # 处理视频列表
        raw_medias = result.get("medias", [])

        # 并发获取每个视频的分P信息
        async def fetch_parts(media):
            bvid = media.get("bvid") or media.get("bv_id")
            if not bvid:
                return media, []

            try:
                pages = await bili.get_video_pagelist(bvid)
                return media, pages
            except Exception as e:
                logger.warning(f"获取分P信息失败 [{bvid}]: {e}")
                return media, []

        tasks = [fetch_parts(m) for m in raw_medias]
        media_parts_results = await asyncio.gather(*tasks) if tasks else []

        await bili.close()

        videos = []
        for media, pages in media_parts_results:
            bvid = media.get("bvid") or media.get("bv_id")
            if not bvid:
                continue
                
            parts = []
            if pages and len(pages) > 1:
                for p in pages:
                    page_num = p.get("page")
                    part_title = p.get("part") or f"P{page_num}"
                    parts.append({
                        "bvid": f"{bvid}_p{page_num}",
                        "title": f"[{page_num}/{len(pages)}] {part_title}",
                        "cid": p.get("cid"),
                        "page": page_num,
                        "duration": p.get("duration")
                    })
                    
            videos.append({
                "bvid": bvid,
                "title": media.get("title"),
                "cover": media.get("cover"),
                "duration": media.get("duration"),
                "owner": media.get("upper", {}).get("name"),
                "play_count": media.get("cnt_info", {}).get("play"),
                "intro": media.get("intro"),
                "is_selected": True,  # 默认选中
                "parts": parts,
                "page_count": len(pages) if pages else 1
            })
        
        return {
            "folder_info": result.get("info"),
            "videos": videos,
            "has_more": result.get("has_more", False),
            "page": page,
            "page_size": page_size
        }
        
    except Exception as e:
        logger.error(f"获取收藏夹视频失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")


@router.get("/{media_id}/all-videos")
async def get_all_favorite_videos(
    media_id: int,
    session_id: str = Query(..., description="会话ID")
):
    """
    获取收藏夹或系列中的所有视频（用于构建知识库）
    支持两种模式：
    1. media_id > 0: 获取收藏夹视频
    2. media_id 是负数或者特殊标记: 获取B站系列视频
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})

    try:
        logger.info(f"获取视频列表: media_id={media_id}")
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )

        # 首先尝试获取收藏夹内容
        all_videos = await bili.get_all_favorite_videos(media_id)
        logger.info(f"[DEBUG] get_all_favorite_videos 返回数量: {len(all_videos)}")
        if all_videos:
            logger.info(f"[DEBUG] 第一个条目的 keys: {list(all_videos[0].keys())}")
            logger.info(f"[DEBUG] 第一个条目的 bvid: {all_videos[0].get('bvid') or all_videos[0].get('bv_id')}")
            logger.info(f"[DEBUG] 第一个条目的 title: {all_videos[0].get('title')}")
            logger.info(f"[DEBUG] 第一个条目的 duration: {all_videos[0].get('duration')}")
            logger.info(f"[DEBUG] 第一个条目的 attr: {all_videos[0].get('attr')}")

        # 如果只返回1个视频，检查是否是系列合集
        if len(all_videos) == 1:
            video = all_videos[0]
            bvid = video.get("bvid") or video.get("bv_id")
            title = video.get("title", "")
            logger.info(f"[DEBUG] 收藏夹只返回1个条目: [{bvid}] {title}")
            if bvid:
                # 获取视频详细信息，检查是否有系列ID
                try:
                    video_info = await bili.get_video_info(bvid)
                    logger.info(f"[DEBUG] video_info keys: {list(video_info.keys()) if isinstance(video_info, dict) else 'not a dict'}")
                    logger.info(f"[DEBUG] video title from API: {video_info.get('title')}")
                    logger.info(f"[DEBUG] season field: {video_info.get('season')}")
                    logger.info(f"[DEBUG] ugc_season field: {video_info.get('ugc_season')}")

                    # 尝试多种方式获取 season_id
                    season_id = None

                    # 方式1: season 是字典 {"id": 123}
                    season = video_info.get("season")
                    if isinstance(season, dict):
                        season_id = season.get("id")
                        logger.info(f"[DEBUG] 从 season dict 获取到: {season_id}")
                    # 方式2: season 是直接的数字或字符串
                    elif season and not isinstance(season, dict):
                        if str(season).isdigit():
                            season_id = int(season)
                            logger.info(f"[DEBUG] 从 season direct 获取到: {season_id}")

                    # 方式3: ugc_season 是字典
                    if not season_id:
                        ugc_season = video_info.get("ugc_season")
                        if isinstance(ugc_season, dict):
                            season_id = ugc_season.get("id")
                            logger.info(f"[DEBUG] 从 ugc_season dict 获取到: {season_id}")
                        # 方式4: ugc_season 是直接的数字或字符串
                        elif ugc_season and not isinstance(ugc_season, dict):
                            if str(ugc_season).isdigit():
                                season_id = int(ugc_season)
                                logger.info(f"[DEBUG] 从 ugc_season direct 获取到: {season_id}")

                    # 方式5: 尝试从页面数据获取系列信息
                    if not season_id:
                        page_data = video_info.get("page_data", {})
                        if page_data:
                            season_id = page_data.get("season_id")
                            logger.info(f"[DEBUG] 从 page_data.season_id 获取到: {season_id}")

                    # 方式6: 检查 series 系列字段
                    if not season_id:
                        series = video_info.get("series")
                        if isinstance(series, dict):
                            season_id = series.get("series_id")
                            logger.info(f"[DEBUG] 从 series.series_id 获取到: {season_id}")
                        elif series and not isinstance(series, dict):
                            if str(series).isdigit():
                                season_id = int(series)
                                logger.info(f"[DEBUG] 从 series direct 获取到: {season_id}")

                    # 方式7: 检查 request_attributes 或其他字段
                    if not season_id:
                        request_attr = video_info.get("request_attribute", {})
                        if isinstance(request_attr, dict):
                            season_id = request_attr.get("season_id")
                            logger.info(f"[DEBUG] 从 request_attribute.season_id 获取到: {season_id}")

                    logger.info(f"[DEBUG] 最终获取的 season_id: {season_id}, 类型: {type(season_id)}")

                    if season_id:
                        logger.info(f"检测到系列ID: {season_id}，获取系列视频列表")
                        series_videos = await bili.get_series_videos(season_id)
                        logger.info(f"[DEBUG] series_videos 长度: {len(series_videos) if series_videos else 0}")
                        if series_videos:
                            logger.info(f"从系列获取到 {len(series_videos)} 个视频")
                            # 检查 series_videos 的第一条数据，确认 title 不是收藏夹标题
                            logger.info(f"[DEBUG] series_videos[0] title: {series_videos[0].get('title') if series_videos else 'N/A'}")
                            all_videos = series_videos
                        else:
                            logger.warning(f"get_series_videos 返回空列表，保留原始数据")
                    else:
                        logger.warning(f"未能获取到 season_id，无法获取系列视频列表")
                        logger.warning(f"[DEBUG] 视频信息可能不是系列的一部分，或者需要检查其他字段")
                        # 打印所有 key 帮助调试
                        if isinstance(video_info, dict):
                            logger.warning(f"[DEBUG] video_info 所有 key: {list(video_info.keys())}")
                except Exception as e:
                    logger.warning(f"检查系列ID失败: {e}")

        import asyncio
        sem = asyncio.Semaphore(5)

        async def process_media(media):
            bvid = media.get("bvid") or media.get("bv_id")
            title = media.get("title", "")
            logger.info(f"[process_media] 输入 media: bvid={bvid}, title='{title}', duration={media.get('duration')}, attr={media.get('attr')}")
            if not bvid:
                logger.warning(f"[process_media] 跳过：bvid 为空")
                return []

            attr = media.get("attr", 0)
            if attr == 9 or title in ["已失效视频", "已删除视频"]:
                logger.warning(f"[process_media] 跳过：attr={attr} 或 title={title}")
                return []

            # 获取视频的正确主标题（用于处理 series 视频的情况）
            video_title = title
            video_info = None
            pages = []

            async with sem:
                try:
                    video_info = await bili.get_video_info(bvid)
                    api_title = video_info.get("title", "")
                    if api_title and api_title != title:
                        logger.info(f"[process_media] 获取到视频主标题: '{api_title}' (原始 title: '{title}')")
                        video_title = api_title
                except Exception as e:
                    logger.warning(f"[process_media] 获取视频信息失败 [{bvid}]: {e}")

                try:
                    pages = await bili.get_video_pagelist(bvid)
                    logger.info(f"[process_media] 分P信息 [{bvid}]: {len(pages) if pages else 0} 页")
                    if pages:
                        logger.info(f"[process_media] 第一P的 part: {pages[0].get('part')}")
                except Exception as e:
                    logger.warning(f"[process_media] 获取分P信息失败 [{bvid}]: {e}")
                    pages = []

            res = []
            if pages and len(pages) > 1:
                logger.info(f"[process_media] [{bvid}] 有 {len(pages)} 个分P，生成多P视频条目")
                for p in pages:
                    page_num = p.get("page")
                    part_title = p.get("part") or f"P{page_num}"
                    # 只保留核心部分（减号后面的内容）
                    core_title = part_title
                    if " - " in part_title:
                        core_title = part_title.split(" - ")[-1].strip()
                    res.append({
                        "bvid": f"{bvid}_p{page_num}",
                        "title": f"[{page_num}/{len(pages)}] {core_title}",
                        "full_title": f"[{page_num}/{len(pages)}] {video_title} - {part_title}",
                        "cover": media.get("cover") or (video_info.get("cover") if video_info else None),
                        "duration": p.get("duration"),
                        "owner": media.get("upper", {}).get("name") if isinstance(media.get("upper"), dict) else media.get("upper"),
                        "cid": p.get("cid"),
                        "original_bvid": bvid,
                        "is_part": True,
                        "part_id": page_num
                    })
            else:
                logger.info(f"[process_media] [{bvid}] 只有 1 个分P或无分P信息，使用视频主标题: {video_title}")
                res.append({
                    "bvid": bvid,
                    "title": video_title,
                    "cover": media.get("cover") or (video_info.get("cover") if video_info else None),
                    "duration": media.get("duration"),
                    "owner": media.get("upper", {}).get("name") if isinstance(media.get("upper"), dict) else media.get("upper"),
                    "cid": media.get("ugc", {}).get("first_cid") if media.get("ugc") else None,
                    "original_bvid": bvid,
                    "is_part": False
                })
            logger.info(f"[process_media] [{bvid}] 返回 {len(res)} 个视频条目")
            return res

        tasks = [process_media(m) for m in all_videos]
        parts_results = await asyncio.gather(*tasks) if tasks else []

        videos = []
        for p_res in parts_results:
            videos.extend(p_res)

        await bili.close()

        logger.info(f"[DEBUG] 最终返回: total={len(videos)}")
        if videos:
            logger.info(f"[DEBUG] 返回的第一个视频 bvid: {videos[0].get('bvid')}")
            logger.info(f"[DEBUG] 返回的第一个视频 title: {videos[0].get('title')}")
            logger.info(f"[DEBUG] 返回的第一个视频 is_part: {videos[0].get('is_part')}")
            logger.info(f"[DEBUG] 返回的第一个视频 original_bvid: {videos[0].get('original_bvid')}")
        return {
            "total": len(videos),
            "videos": videos
        }

    except Exception as e:
        logger.error(f"获取所有视频失败: {e}")
        if 'bili' in locals():
            await bili.close()
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")


@router.post("/organize/preview", response_model=OrganizePreviewResponse)
async def organize_preview(
    payload: OrganizePreviewRequest,
    session_id: str = Query(..., description="会话ID"),
):
    """
    预览：按已有收藏夹名称对默认收藏夹内容分类
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})
    user_info = session.get("user_info", {})

    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID"),
        )
        mid = user_info.get("mid") or cookies.get("DedeUserID")
        folders = await bili.get_user_favorites(mid=mid)
        default_folder = next((f for f in folders if _is_default_folder(f)), None)
        if not default_folder:
            raise HTTPException(status_code=400, detail="未找到默认收藏夹")

        default_folder_id = default_folder.get("id")
        if payload.folder_id and payload.folder_id != default_folder_id:
            logger.warning("传入的默认收藏夹ID不匹配，已使用接口默认收藏夹")

        candidate_folders = [f for f in folders if f.get("id") != default_folder_id]

        videos = await bili.get_all_favorite_videos(default_folder_id)

        items_data = []
        for media in videos:
            bvid = media.get("bvid") or media.get("bv_id")
            title = media.get("title") or bvid or ""
            if not bvid:
                continue
            attr = media.get("attr", 0)
            if attr == 9 or title in ["已失效视频", "已删除视频"]:
                continue

            resource_id = media.get("id") or media.get("aid") or media.get("avid")
            if not resource_id:
                continue
            try:
                resource_id = int(resource_id)
            except Exception:
                continue
            resource_type = media.get("type") or 2
            try:
                resource_type = int(resource_type)
            except Exception:
                resource_type = 2
            items_data.append(
                {
                    "bvid": bvid,
                    "title": title,
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                }
            )

        items: List[OrganizePreviewItem] = []
        matched = 0
        for idx, item in enumerate(items_data):
            target_folder_id = None
            target_folder_title = default_folder.get("title", "默认收藏夹")
            reason = "待手动分类"
            items.append(
                OrganizePreviewItem(
                    bvid=item["bvid"],
                    title=item["title"],
                    resource_id=item["resource_id"],
                    resource_type=item["resource_type"],
                    target_folder_id=target_folder_id,
                    target_folder_title=target_folder_title,
                    reason=reason,
                )
            )

        await bili.close()

        folders_payload = [
            FavoriteFolderInfo(
                media_id=f.get("id"),
                title=f.get("title"),
                media_count=f.get("media_count", 0),
                is_selected=True,
                is_default=False,
            )
            for f in candidate_folders
        ]

        return OrganizePreviewResponse(
            default_folder_id=default_folder_id,
            default_folder_title=default_folder.get("title", "默认收藏夹"),
            folders=folders_payload,
            items=items,
            stats={
                "total": len(items),
                "matched": matched,
                "unmatched": len(items) - matched,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"收藏夹整理预览失败: {e}")
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.post("/organize/execute")
async def organize_execute(
    payload: OrganizeExecuteRequest,
    session_id: str = Query(..., description="会话ID"),
):
    """
    执行：根据预览结果批量移动收藏夹内容
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})

    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID"),
        )

        move_groups: dict[int, List[str]] = {}
        for item in payload.moves:
            if item.target_folder_id == payload.default_folder_id:
                continue
            resources = move_groups.setdefault(item.target_folder_id, [])
            resources.append(f"{item.resource_id}:{item.resource_type}")

        total_moved = 0
        for target_id, resources in move_groups.items():
            if not resources:
                continue
            await bili.move_favorite_resources(
                src_media_id=payload.default_folder_id,
                tar_media_id=target_id,
                resources=resources,
            )
            total_moved += len(resources)

        await bili.close()

        return {
            "message": "移动完成",
            "moved": total_moved,
            "groups": len(move_groups),
        }
    except Exception as e:
        logger.error(f"收藏夹整理执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/organize/clean-invalid")
async def clean_invalid_resources(
    payload: CleanInvalidRequest,
    session_id: str = Query(..., description="会话ID"),
):
    """
    清理收藏夹失效内容
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})

    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID"),
        )
        data = await bili.clean_favorite_resources(payload.folder_id)
        await bili.close()
        return {"message": "清理完成", "data": data}
    except Exception as e:
        logger.error(f"清理失效内容失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")
