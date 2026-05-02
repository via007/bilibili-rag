"""
计费/用量查询接口

提供用户 LLM 用量的聚合查询：
- 总 token / 调用次数
- 按 Provider 分布（饼图数据）
- 按 Credential 分布（树状图数据）
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import UsageSummary
from app.routers.auth import get_session
from app.repository.usage_repository import get_usage_repository

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary(
    session_id: str = Query(..., description="会话ID"),
    days: int = Query(30, description="统计天数", ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """获取用量汇总（总 token + 调用次数 + 按 provider/credential 分布）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    repo = get_usage_repository()
    summary = await repo.get_summary(session_id, db, days=days)
    return summary


@router.get("/by-provider")
async def get_usage_by_provider(
    session_id: str = Query(..., description="会话ID"),
    days: int = Query(30, description="统计天数", ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """按 Provider 聚合用量（饼图数据）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    repo = get_usage_repository()
    return await repo.get_by_provider(session_id, db, days=days)


@router.get("/by-credential")
async def get_usage_by_credential(
    session_id: str = Query(..., description="会话ID"),
    days: int = Query(30, description="统计天数", ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """按 Credential 聚合用量（树状图数据）。"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    repo = get_usage_repository()
    return await repo.get_by_credential(session_id, db, days=days)
