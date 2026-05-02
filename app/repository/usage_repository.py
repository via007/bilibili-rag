"""
UsageRepository — credential_usage 表的数据库操作

职责：用量记录写入 + 聚合查询（按 provider / credential 分组）。
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import CredentialUsage, UsageSummary, ProviderUsage, CredentialUsageItem
from app.models import UserCredential


class UsageRepository:
    """credential_usage 表的数据访问层"""

    async def record(
        self,
        session_id: str,
        credential_id: Optional[int],
        provider: Optional[str],
        model: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
        db: AsyncSession,
    ) -> None:
        """记录一次 LLM 调用的 token 用量"""
        total = prompt_tokens + completion_tokens
        entry = CredentialUsage(
            session_id=session_id,
            credential_id=credential_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            api_calls=1,
        )
        db.add(entry)
        await db.commit()
        logger.debug(
            f"[USAGE_REPO] recorded provider={provider} tokens={total} "
            f"credential_id={credential_id} session={session_id[:8]}..."
        )

    async def get_summary(
        self, session_id: str, db: AsyncSession, days: int = 30
    ) -> UsageSummary:
        """获取用户用量汇总（总 token + 调用次数 + 按 provider/credential 分布）"""
        since = datetime.utcnow() - timedelta(days=days)

        # 总 token + 调用次数
        total_result = await db.execute(
            select(
                func.coalesce(func.sum(CredentialUsage.total_tokens), 0),
                func.coalesce(func.sum(CredentialUsage.api_calls), 0),
            ).where(
                CredentialUsage.session_id == session_id,
                CredentialUsage.created_at >= since,
            )
        )
        total_tokens, total_api_calls = total_result.one()

        by_provider = await self.get_by_provider(session_id, db, days)
        by_credential = await self.get_by_credential(session_id, db, days)

        return UsageSummary(
            total_tokens=total_tokens,
            total_api_calls=total_api_calls,
            by_provider=by_provider,
            by_credential=by_credential,
        )

    async def get_by_provider(
        self, session_id: str, db: AsyncSession, days: int = 30
    ) -> list[ProviderUsage]:
        """按 provider 聚合用量（饼图数据）"""
        since = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(
                CredentialUsage.provider,
                func.sum(CredentialUsage.total_tokens).label("total_tokens"),
                func.sum(CredentialUsage.api_calls).label("api_calls"),
            )
            .where(
                CredentialUsage.session_id == session_id,
                CredentialUsage.created_at >= since,
            )
            .group_by(CredentialUsage.provider)
            .order_by(func.sum(CredentialUsage.total_tokens).desc())
        )
        rows = result.all()
        return [
            ProviderUsage(
                provider=row.provider or "unknown",
                total_tokens=row.total_tokens,
                api_calls=row.api_calls,
                cost_estimate=0.0,
            )
            for row in rows
        ]

    async def get_by_credential(
        self, session_id: str, db: AsyncSession, days: int = 30
    ) -> list[CredentialUsageItem]:
        """按 credential 聚合用量（树状图数据），NULL credential_id = 系统默认"""
        since = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(
                CredentialUsage.credential_id,
                CredentialUsage.provider,
                func.sum(CredentialUsage.total_tokens).label("total_tokens"),
                func.sum(CredentialUsage.api_calls).label("api_calls"),
            )
            .where(
                CredentialUsage.session_id == session_id,
                CredentialUsage.created_at >= since,
            )
            .group_by(CredentialUsage.credential_id, CredentialUsage.provider)
            .order_by(func.sum(CredentialUsage.total_tokens).desc())
        )
        rows = result.all()

        # 查询 credential 名称
        cred_ids = [r.credential_id for r in rows if r.credential_id is not None]
        name_map: dict[int, str] = {}
        if cred_ids:
            name_result = await db.execute(
                select(UserCredential.id, UserCredential.name).where(
                    UserCredential.id.in_(cred_ids)
                )
            )
            name_map = {row.id: row.name for row in name_result.all()}

        items = []
        for row in rows:
            if row.credential_id is None:
                name = "系统默认"
            else:
                name = name_map.get(row.credential_id, f"Credential #{row.credential_id}")

            items.append(
                CredentialUsageItem(
                    credential_id=row.credential_id,
                    name=name,
                    provider=row.provider or "unknown",
                    total_tokens=row.total_tokens,
                    api_calls=row.api_calls,
                    cost_estimate=0.0,
                )
            )
        return items

    async def batch_record(
        self, records: list[dict], db: AsyncSession
    ) -> None:
        """批量 INSERT 用量记录（单条 SQL，单次事务）"""
        if not records:
            return
        stmt = insert(CredentialUsage).values(records)
        await db.execute(stmt)
        await db.commit()
        logger.debug(f"[USAGE_REPO] batch inserted {len(records)} usage records")

    async def cleanup_old(self, db: AsyncSession, days: int = 90) -> int:
        """清理超过 N 天的用量记录，返回删除行数"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            delete(CredentialUsage).where(CredentialUsage.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        if deleted:
            logger.info(f"[USAGE_REPO] cleaned up {deleted} old usage records")
        return deleted


# 模块级单例
_usage_repo: Optional[UsageRepository] = None


def get_usage_repository() -> UsageRepository:
    """获取 UsageRepository 单例"""
    global _usage_repo
    if _usage_repo is None:
        _usage_repo = UsageRepository()
    return _usage_repo
