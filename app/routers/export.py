"""
Bilibili RAG 知识库系统
导出 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Literal, List
from loguru import logger

from app.database import get_db
from app.services.export import ExportService


router = APIRouter(prefix="/export", tags=["导出"])


class ExportVideoRequest(BaseModel):
    """导出视频请求"""
    bvid: str
    format: Literal["full", "simple"] = "full"


class ExportFolderRequest(BaseModel):
    """导出收藏夹请求"""
    folder_ids: List[int]  # 支持多选
    format: Literal["full", "simple"] = "full"


class ExportSessionRequest(BaseModel):
    """导出会话请求"""
    chat_session_id: str


class ExportSessionSummaryRequest(BaseModel):
    """导出会话总结请求"""
    chat_session_id: str
    format: Literal["full", "simple"] = "full"


@router.post("/video")
async def export_video(
    request: ExportVideoRequest,
    db: AsyncSession = Depends(get_db)
):
    """导出单个视频"""
    try:
        service = ExportService(db)
        result = await service.export_video(request.bvid, request.format)
        return {
            "success": True,
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"导出视频失败: {e}")
        raise HTTPException(status_code=500, detail="导出失败")


@router.post("/folder")
async def export_folder(
    request: ExportFolderRequest,
    db: AsyncSession = Depends(get_db)
):
    """导出收藏夹（支持单或多选）"""
    try:
        service = ExportService(db)
        result = await service.export_folders(request.folder_ids, request.format)
        return {
            "success": True,
            **result
        }
    except Exception as e:
        logger.error(f"导出收藏夹失败: {e}")
        raise HTTPException(status_code=500, detail="导出失败")


@router.post("/session")
async def export_session(
    request: ExportSessionRequest,
    db: AsyncSession = Depends(get_db)
):
    """导出会话"""
    try:
        service = ExportService(db)
        result = await service.export_session(request.chat_session_id)
        return {
            "success": True,
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"导出会话失败: {e}")
        raise HTTPException(status_code=500, detail="导出失败")


@router.get("/session-summary/{chat_session_id}")
async def get_session_summary(
    chat_session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取会话总结（优先缓存）"""
    try:
        service = ExportService(db)
        result = await service.get_session_summary(chat_session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取会话总结失败: {e}")
        raise HTTPException(status_code=500, detail="获取失败")


@router.post("/session-summary/{chat_session_id}/refresh")
async def refresh_session_summary(
    chat_session_id: str,
    request: ExportSessionSummaryRequest,
    db: AsyncSession = Depends(get_db)
):
    """刷新会话总结（重新生成）"""
    try:
        service = ExportService(db)
        result = await service.refresh_session_summary(chat_session_id, request.format)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"刷新会话总结失败: {e}")
        raise HTTPException(status_code=500, detail="刷新失败")


@router.delete("/session-summary/{chat_session_id}")
async def delete_session_summary(
    chat_session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除会话总结缓存"""
    try:
        service = ExportService(db)
        await service.delete_session_summary(chat_session_id)
        return {"success": True, "message": "缓存已删除"}
    except Exception as e:
        logger.error(f"删除会话总结失败: {e}")
        raise HTTPException(status_code=500, detail="删除失败")
