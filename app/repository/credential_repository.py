"""
CredentialRepository — user_credentials 表的数据库 CRUD 操作

职责：封装对 user_credentials 表的所有数据库访问。
注意：不包含加密/解密逻辑（由 services/llm/api_key_manager.py 负责）。
"""
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import UserCredential


class CredentialRepository:
    """user_credentials 表的数据访问层"""

    async def list_by_session(
        self, session_id: str, db: AsyncSession
    ) -> list[UserCredential]:
        """列出用户的全部 credential（按 updated_at 倒序）"""
        result = await db.execute(
            select(UserCredential)
            .where(UserCredential.session_id == session_id)
            .order_by(UserCredential.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(
        self, credential_id: int, db: AsyncSession
    ) -> Optional[UserCredential]:
        """根据 ID 查询单个 credential"""
        result = await db.execute(
            select(UserCredential).where(UserCredential.id == credential_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        session_id: str,
        name: str,
        provider: str,
        api_key_encrypted: str,
        base_url: Optional[str],
        default_model: Optional[str],
        is_default: bool,
        db: AsyncSession,
    ) -> UserCredential:
        """新建 credential。若 is_default=True，先清除同 session 其他默认。"""
        if is_default:
            await self._clear_default(session_id, db)

        record = UserCredential(
            session_id=session_id,
            name=name,
            provider=provider,
            api_key_encrypted=api_key_encrypted,
            base_url=base_url,
            default_model=default_model,
            is_default=is_default,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(
            f"[CRED_REPO] created id={record.id} provider={provider} "
            f"session={session_id[:8]}..."
        )
        return record

    async def update(
        self,
        credential_id: int,
        db: AsyncSession,
        name: Optional[str] = None,
        api_key_encrypted: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        is_default: Optional[bool] = None,
    ) -> Optional[UserCredential]:
        """部分更新 credential。返回更新后的记录，不存在返回 None。"""
        record = await self.get_by_id(credential_id, db)
        if record is None:
            return None

        if name is not None:
            record.name = name
        if api_key_encrypted is not None:
            record.api_key_encrypted = api_key_encrypted
        if base_url is not None:
            record.base_url = base_url
        if default_model is not None:
            record.default_model = default_model
        if is_default:
            await self._clear_default(record.session_id, db, exclude_id=credential_id)
            record.is_default = True

        await db.commit()
        await db.refresh(record)
        logger.info(f"[CRED_REPO] updated id={credential_id}")
        return record

    async def delete(self, credential_id: int, db: AsyncSession) -> bool:
        """删除 credential。返回 True 表示删除成功，False 表示不存在。"""
        record = await self.get_by_id(credential_id, db)
        if record is None:
            return False
        await db.delete(record)
        await db.commit()
        logger.info(f"[CRED_REPO] deleted id={credential_id}")
        return True

    async def set_default(
        self, session_id: str, credential_id: int, db: AsyncSession
    ) -> bool:
        """将指定 credential 设为默认（原子操作：先清默认，再设这个）。"""
        record = await self.get_by_id(credential_id, db)
        if record is None or record.session_id != session_id:
            return False

        await self._clear_default(session_id, db, exclude_id=credential_id)
        record.is_default = True
        await db.commit()
        await db.refresh(record)
        logger.info(f"[CRED_REPO] set_default id={credential_id} session={session_id[:8]}...")
        return True

    async def get_default(
        self, session_id: str, db: AsyncSession
    ) -> Optional[UserCredential]:
        """获取用户的默认 credential"""
        result = await db.execute(
            select(UserCredential).where(
                UserCredential.session_id == session_id,
                UserCredential.is_default == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _clear_default(
        self,
        session_id: str,
        db: AsyncSession,
        exclude_id: Optional[int] = None,
    ) -> None:
        """清除该 session 下所有 credential 的 is_default 标志"""
        stmt = (
            update(UserCredential)
            .where(
                UserCredential.session_id == session_id,
                UserCredential.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )
        if exclude_id is not None:
            stmt = stmt.where(UserCredential.id != exclude_id)
        await db.execute(stmt)


# 模块级单例
_credential_repo: Optional[CredentialRepository] = None


def get_credential_repository() -> CredentialRepository:
    """获取 CredentialRepository 单例"""
    global _credential_repo
    if _credential_repo is None:
        _credential_repo = CredentialRepository()
    return _credential_repo
