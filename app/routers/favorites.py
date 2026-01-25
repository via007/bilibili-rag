"""
Bilibili RAG 知识库系统

收藏夹路由
"""
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from typing import List, Optional
from app.models import FavoriteFolderInfo
from app.services.bilibili import BilibiliService
from app.routers.auth import get_session

router = APIRouter(prefix="/favorites", tags=["收藏夹"])


@router.get("/list", response_model=List[FavoriteFolderInfo])
async def get_favorites_list(session_id: str = Query(..., description="会话ID")):
    """
    获取用户的收藏夹列表
    """
    session = get_session(session_id)
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
                is_selected=True
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
    session = get_session(session_id)
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
        await bili.close()
        
        # 处理视频列表
        videos = []
        for media in result.get("medias", []):
            videos.append({
                "bvid": media.get("bvid") or media.get("bv_id"),
                "title": media.get("title"),
                "cover": media.get("cover"),
                "duration": media.get("duration"),
                "owner": media.get("upper", {}).get("name"),
                "play_count": media.get("cnt_info", {}).get("play"),
                "intro": media.get("intro"),
                "is_selected": True  # 默认选中
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
    获取收藏夹中的所有视频（用于构建知识库）
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    
    cookies = session.get("cookies", {})
    
    try:
        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID")
        )
        
        all_videos = await bili.get_all_favorite_videos(media_id)
        await bili.close()
        
        # 处理视频列表（过滤失效视频）
        videos = []
        for media in all_videos:
            bvid = media.get("bvid") or media.get("bv_id")
            title = media.get("title", "")
            if not bvid:
                continue
            
            # 过滤失效视频
            attr = media.get("attr", 0)
            if attr == 9 or title in ["已失效视频", "已删除视频"]:
                continue
                
            videos.append({
                "bvid": bvid,
                "title": title,
                "cover": media.get("cover"),
                "duration": media.get("duration"),
                "owner": media.get("upper", {}).get("name"),
                "cid": media.get("ugc", {}).get("first_cid") if media.get("ugc") else None
            })
        
        return {
            "total": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"获取所有视频失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")
