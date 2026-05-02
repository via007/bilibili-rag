"""
UserSettings Repository — user_settings 表的数据库 CRUD 操作

职责：封装对 user_settings 表的所有数据库访问。
注意：不包含加密/解密逻辑（由 services/llm/api_key_manager.py 负责）。
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import UserSettings


class UserSettingsRepository:
    """user_settings 表的数据访问层"""

    async def get_by_session_id(
        self, session_id: str, db: AsyncSession
    ) -> Optional[UserSettings]:
        """根据 session_id 查询配置，返回 None 表示未配置"""
        result = await db.execute(
            select(UserSettings).where(UserSettings.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        session_id: str,
        db: AsyncSession,
        llm_api_key_encrypted: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        embedding_api_key_encrypted: Optional[str] = None,
        embedding_base_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        asr_api_key_encrypted: Optional[str] = None,
        asr_base_url: Optional[str] = None,
        asr_model: Optional[str] = None,
    ) -> UserSettings:
        """
        写入或更新用户配置（部分更新：只更新非 None 字段）。
        返回最新的 UserSettings 记录。
        """
        result = await db.execute(
            select(UserSettings).where(UserSettings.session_id == session_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = UserSettings(session_id=session_id)
            db.add(record)

        if llm_api_key_encrypted is not None:
            record.llm_api_key_encrypted = llm_api_key_encrypted
        if llm_base_url is not None:
            record.llm_base_url = llm_base_url
        if llm_model is not None:
            record.llm_model = llm_model
        if embedding_api_key_encrypted is not None:
            record.embedding_api_key_encrypted = embedding_api_key_encrypted
        if embedding_base_url is not None:
            record.embedding_base_url = embedding_base_url
        if embedding_model is not None:
            record.embedding_model = embedding_model
        if asr_api_key_encrypted is not None:
            record.asr_api_key_encrypted = asr_api_key_encrypted
        if asr_base_url is not None:
            record.asr_base_url = asr_base_url
        if asr_model is not None:
            record.asr_model = asr_model

        await db.commit()
        await db.refresh(record)
        logger.info(f"[REPO] user_settings upserted for session={session_id[:8]}...")
        return record

    async def delete(self, session_id: str, db: AsyncSession) -> bool:
        """
        删除用户的所有自定义 API Key 配置。
        返回 True 表示有记录被删除，False 表示本来就没有配置。
        """
        result = await db.execute(
            select(UserSettings).where(UserSettings.session_id == session_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            return False

        await db.delete(record)
        await db.commit()
        logger.info(f"[REPO] user_settings deleted for session={session_id[:8]}...")
        return True


# 模块级单例
_user_settings_repo: Optional[UserSettingsRepository] = None


def get_user_settings_repository() -> UserSettingsRepository:
    """获取 UserSettingsRepository 单例"""
    global _user_settings_repo
    if _user_settings_repo is None:
        _user_settings_repo = UserSettingsRepository()
    return _user_settings_repo
