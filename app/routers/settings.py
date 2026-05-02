"""
用户 API Key 配置接口

提供用户自定义 LLM/Embedding API Key 的增删查接口。
所有接口需验证 session，响应中绝不包含完整 Key。
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import ApiKeySetRequest, ApiKeyStatusResponse
from app.routers.auth import get_session
from app.services.llm.api_key_manager import ApiKeyManager

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_api_key_manager() -> ApiKeyManager:
    """获取全局 ApiKeyManager 实例（通过 app.state 注入）。"""
    from app.main import app
    manager: ApiKeyManager = app.state.api_key_manager
    if not manager:
        raise HTTPException(status_code=503, detail="API Key 配置功能暂不可用")
    return manager


@router.get("/credentials/status", response_model=ApiKeyStatusResponse)
async def get_credentials_status(
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户 LLM + Embedding 配置状态（不返回完整 Key）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    status = await manager.get_status(session_id, db)
    return ApiKeyStatusResponse(**status)


@router.post("/credentials")
async def set_credentials(
    req: ApiKeySetRequest,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """设置/更新用户 API Key（支持部分更新）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    # 基础校验：至少有一个字段被设置
    has_any = any([
        req.llm_api_key, req.llm_base_url, req.llm_model,
        req.embedding_api_key, req.embedding_base_url, req.embedding_model,
        req.asr_api_key, req.asr_base_url, req.asr_model,
    ])
    if not has_any:
        raise HTTPException(status_code=400, detail="请至少填写一个配置项")

    manager = _get_api_key_manager()
    try:
        await manager.set_credentials(
            session_id=session_id,
            llm_key=req.llm_api_key,
            llm_base_url=req.llm_base_url,
            llm_model=req.llm_model,
            embedding_key=req.embedding_api_key,
            embedding_base_url=req.embedding_base_url,
            embedding_model=req.embedding_model,
            asr_key=req.asr_api_key,
            asr_base_url=req.asr_base_url,
            asr_model=req.asr_model,
            db=db,
        )
        logger.info(f"[SETTINGS] API keys updated for session={session_id[:8]}...")
        return {"message": "API Key 配置已保存"}
    except Exception as e:
        logger.error(f"[SETTINGS] Failed to save credentials: {e}")
        raise HTTPException(status_code=500, detail="配置保存失败")


@router.delete("/credentials")
async def delete_credentials(
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """删除用户所有自定义 API Key，回退到系统默认（会产生费用）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    await manager.delete_credentials(session_id, db)
    logger.info(f"[SETTINGS] API keys deleted for session={session_id[:8]}...")
    return {"message": "已删除自定义 API Key，将使用系统默认配置（可能产生费用）"}
