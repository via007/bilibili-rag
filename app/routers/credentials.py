"""
多 Provider Credential 管理接口

提供用户自定义多个 LLM API Key（OpenAI / Anthropic / DeepSeek / Custom）的 CRUD 接口。
所有接口需验证 session，响应中绝不包含完整 Key。
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import CredentialCreate, CredentialUpdate, CredentialResponse
from app.routers.auth import get_session
from app.services.llm.api_key_manager import ApiKeyManager

router = APIRouter(prefix="/credentials", tags=["credentials"])


def _get_api_key_manager() -> ApiKeyManager:
    """获取全局 ApiKeyManager 实例（通过 app.state 注入）。"""
    from app.main import app
    manager: ApiKeyManager = app.state.api_key_manager
    if not manager:
        raise HTTPException(status_code=503, detail="API Key 配置功能暂不可用")
    return manager


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的全部 credential（Key 已 mask）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    return await manager.list_credentials(session_id, db)


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    req: CredentialCreate,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """新建 credential。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    if not req.api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    if req.provider not in ("openai", "anthropic", "deepseek", "custom"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 provider: {req.provider}，可选: openai / anthropic / deepseek / custom",
        )

    manager = _get_api_key_manager()
    try:
        return await manager.create_credential(
            session_id=session_id,
            name=req.name,
            provider=req.provider,
            api_key=req.api_key,
            base_url=req.base_url,
            default_model=req.default_model,
            is_default=req.is_default,
            db=db,
        )
    except Exception as e:
        logger.error(f"[CREDENTIALS] create failed: {e}")
        raise HTTPException(status_code=500, detail="Credential 创建失败")


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: int,
    req: CredentialUpdate,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """部分更新 credential。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    result = await manager.update_credential(
        session_id=session_id,
        credential_id=credential_id,
        name=req.name,
        api_key=req.api_key,
        base_url=req.base_url,
        default_model=req.default_model,
        is_default=req.is_default,
        db=db,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Credential 不存在")
    return result


@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: int,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """删除 credential。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    deleted = await manager.delete_credential(session_id, credential_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential 不存在")
    return {"message": "Credential 已删除"}


@router.post("/{credential_id}/default")
async def set_default_credential(
    credential_id: int,
    session_id: str = Query(..., description="会话ID"),
    db: AsyncSession = Depends(get_db),
):
    """将指定 credential 设为默认。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    manager = _get_api_key_manager()
    ok = await manager.set_default(session_id, credential_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Credential 不存在或不属于当前用户")
    return {"message": "已设为默认"}
