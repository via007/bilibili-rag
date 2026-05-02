"""
API Key Manager — 用户多 Provider API Key 的加密存储、缓存和动态解析

职责：
1. AES-256-GCM 加密/解密
2. 多 credential CRUD（list / create / update / delete / set_default）
3. 通过 CredentialCacheBackend 缓存 credential 数据
4. 提供 get_default_credential_sync 接口供 chat.py 同步调用
5. Key mask 展示

缓存策略：
- 本期使用 LocalMemoryCache（dict + TTL 5 分钟）
- 后续可替换为 RedisCache（实现 CredentialCacheBackend 接口即可）
- 缓存 key = session_id，存储该 session 的所有 credential
"""
import base64
import os
import time
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.repository.credential_repository import (
    CredentialRepository,
    get_credential_repository,
)
from app.repository.usage_repository import (
    UsageRepository,
    get_usage_repository,
)
from app.repository.user_settings_repository import (
    UserSettingsRepository,
    get_user_settings_repository,
)
from app.services.llm.credential_cache import (
    CredentialCacheBackend,
    CredentialCacheData,
    CacheEntry,
    LocalMemoryCache,
)

# Import models for type hints
from app.models import CredentialResponse


@dataclass
class UserCredentials:
    """用户凭据（临时持有，用完即释放）"""
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    credential_id: Optional[int] = None  # None = 系统默认


class ApiKeyManager:
    """
    用户多 Provider API Key 管理器

    关键安全原则：
    - 数据库存密文
    - 缓存只存密文
    - 使用时临时解密，用完即释放
    """

    CACHE_TTL = 300  # 5 分钟

    def __init__(
        self,
        encryption_key_b64: Optional[str] = None,
        cache_backend: Optional[CredentialCacheBackend] = None,
        credential_repo: Optional[CredentialRepository] = None,
        usage_repo: Optional[UsageRepository] = None,
        user_settings_repo: Optional[UserSettingsRepository] = None,
    ):
        self._cache = cache_backend or LocalMemoryCache()
        self._cred_repo = credential_repo or get_credential_repository()
        self._usage_repo = usage_repo or get_usage_repository()
        self._user_settings_repo = user_settings_repo or get_user_settings_repository()
        self._enabled = True

        if encryption_key_b64:
            try:
                key_bytes = base64.b64decode(encryption_key_b64)
                if len(key_bytes) != 32:
                    raise ValueError(f"Key is {len(key_bytes)} bytes, expected 32")
                self._aesgcm = AESGCM(key_bytes)
                logger.info("[API_KEY_MANAGER] initialized with AES-256-GCM encryption")
            except Exception as e:
                self._aesgcm = None
                logger.warning(
                    f"[API_KEY_MANAGER] invalid encryption key ({e}), "
                    "API keys will be stored WITHOUT encryption"
                )
        else:
            self._aesgcm = None
            logger.warning(
                "[API_KEY_MANAGER] encryption key not configured, "
                "API keys will be stored WITHOUT encryption"
            )

    # ═══════════════════════════════════════════════════════════
    # 多 Credential CRUD
    # ═══════════════════════════════════════════════════════════

    async def list_credentials(
        self, session_id: str, db: AsyncSession
    ) -> list[CredentialResponse]:
        """列出用户全部 credential（Key masked）"""
        records = await self._cred_repo.list_by_session(session_id, db)
        return [
            CredentialResponse(
                id=r.id,
                name=r.name,
                provider=r.provider,
                masked_key=self._mask_key(self._decrypt(r.api_key_encrypted)),
                base_url=r.base_url,
                default_model=r.default_model,
                is_default=r.is_default,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ]

    async def create_credential(
        self,
        session_id: str,
        name: str,
        provider: str,
        api_key: str,
        base_url: Optional[str],
        default_model: Optional[str],
        is_default: bool,
        db: AsyncSession,
    ) -> CredentialResponse:
        """新建 credential，同时刷新缓存"""
        record = await self._cred_repo.create(
            session_id=session_id,
            name=name,
            provider=provider,
            api_key_encrypted=self._encrypt(api_key),
            base_url=base_url,
            default_model=default_model,
            is_default=is_default,
            db=db,
        )
        # 刷新缓存
        await self._refresh_cache(session_id, db)
        return CredentialResponse(
            id=record.id,
            name=record.name,
            provider=record.provider,
            masked_key=self._mask_key(api_key),
            base_url=record.base_url,
            default_model=record.default_model,
            is_default=record.is_default,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def update_credential(
        self,
        session_id: str,
        credential_id: int,
        name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        is_default: Optional[bool] = None,
        db: AsyncSession = None,
    ) -> Optional[CredentialResponse]:
        """部分更新 credential"""
        api_key_encrypted = self._encrypt(api_key) if api_key else None

        record = await self._cred_repo.update(
            credential_id=credential_id,
            db=db,
            name=name,
            api_key_encrypted=api_key_encrypted,
            base_url=base_url,
            default_model=default_model,
            is_default=is_default,
        )
        if record is None:
            return None

        # 刷新缓存
        await self._refresh_cache(session_id, db)
        return CredentialResponse(
            id=record.id,
            name=record.name,
            provider=record.provider,
            masked_key=self._mask_key(self._decrypt(record.api_key_encrypted)),
            base_url=record.base_url,
            default_model=record.default_model,
            is_default=record.is_default,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def delete_credential(
        self, session_id: str, credential_id: int, db: AsyncSession
    ) -> bool:
        """删除 credential"""
        deleted = await self._cred_repo.delete(credential_id, db)
        if deleted:
            await self._refresh_cache(session_id, db)
        return deleted

    async def set_default(
        self, session_id: str, credential_id: int, db: AsyncSession
    ) -> bool:
        """设为默认 credential"""
        ok = await self._cred_repo.set_default(session_id, credential_id, db)
        if ok:
            await self._refresh_cache(session_id, db)
        return ok

    async def get_default_credential(
        self, session_id: str, db: AsyncSession
    ) -> Optional[UserCredentials]:
        """异步获取用户默认 LLM credential"""
        entry = await self._get_cache_entry(session_id, db)
        if entry is None or entry.default_credential_id is None:
            return None

        cred_data = entry.credentials.get(entry.default_credential_id)
        if cred_data is None:
            return None

        try:
            return UserCredentials(
                api_key=self._decrypt(cred_data.api_key_encrypted),
                base_url=cred_data.base_url,
                model=cred_data.default_model,
                credential_id=entry.default_credential_id,
            )
        except Exception as e:
            logger.error(f"[API_KEY_MANAGER] decrypt default cred failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════
    # 同步方法（供 chat.py 的同步 _get_llm 使用）
    # ═══════════════════════════════════════════════════════════

    def get_default_credential_sync(
        self, session_id: Optional[str]
    ) -> Optional[UserCredentials]:
        """
        同步获取用户默认 LLM credential（仅读缓存，不查数据库）。

        用于 chat.py 的同步 _get_llm() 函数。
        缓存未命中时返回 None，调用方应使用系统默认 Key。
        """
        import asyncio

        if not session_id or not self._enabled:
            return None

        # 同步调用异步缓存读取（仅内存 dict 操作，无阻塞风险）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在运行中的 event loop 中，用 run_coroutine_threadsafe 或直接同步读
                # LocalMemoryCache 的 get 只涉及 dict + time，可以安全地用 future
                future = asyncio.run_coroutine_threadsafe(
                    self._cache.get(session_id), loop
                )
                entry = future.result(timeout=0.5)
            else:
                entry = loop.run_until_complete(self._cache.get(session_id))
        except RuntimeError:
            # 没有事件循环（不应该发生），直接无法获取
            return None
        except Exception:
            return None

        if entry is None or entry.default_credential_id is None:
            return None

        cred_data = entry.credentials.get(entry.default_credential_id)
        if cred_data is None:
            return None

        try:
            return UserCredentials(
                api_key=self._decrypt(cred_data.api_key_encrypted),
                base_url=cred_data.base_url,
                model=cred_data.default_model,
                credential_id=entry.default_credential_id,
            )
        except Exception as e:
            logger.error(f"[API_KEY_MANAGER] sync decrypt failed: {e}")
            return None

    async def preload_credentials(self, session_id: str, db: AsyncSession) -> None:
        """预热缓存（在请求入口的异步上下文中调用）"""
        if not session_id or not self._enabled:
            return
        await self._get_cache_entry(session_id, db)

    # ═══════════════════════════════════════════════════════════
    # 兼容旧 settings 接口（deprecated，后续移除）
    # ═══════════════════════════════════════════════════════════

    async def get_llm_credentials(
        self, session_id: Optional[str], db: AsyncSession
    ) -> Optional[UserCredentials]:
        """[deprecated] 获取用户 LLM 配置 — 等同于 get_default_credential"""
        return await self.get_default_credential(session_id, db)

    async def set_credentials(
        self,
        session_id: str,
        llm_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        embedding_key: Optional[str] = None,
        embedding_base_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        asr_key: Optional[str] = None,
        asr_base_url: Optional[str] = None,
        asr_model: Optional[str] = None,
        db: AsyncSession = None,
    ) -> None:
        """[deprecated] 旧 settings 写入接口 — 委托到 user_settings_repo"""
        await self._user_settings_repo.upsert(
            session_id=session_id,
            db=db,
            llm_api_key_encrypted=self._encrypt(llm_key) if llm_key else None,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            embedding_api_key_encrypted=self._encrypt(embedding_key) if embedding_key else None,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            asr_api_key_encrypted=self._encrypt(asr_key) if asr_key else None,
            asr_base_url=asr_base_url,
            asr_model=asr_model,
        )
        await self._cache.delete(session_id)
        logger.info(f"[API_KEY_MANAGER] credentials updated for session={session_id[:8]}...")

    async def delete_credentials(self, session_id: str, db: AsyncSession) -> None:
        """[deprecated] 旧 settings 删除接口"""
        await self._user_settings_repo.delete(session_id, db)
        await self._cache.delete(session_id)
        logger.info(f"[API_KEY_MANAGER] credentials deleted for session={session_id[:8]}...")

    async def get_status(self, session_id: str, db: AsyncSession) -> dict:
        """[deprecated] 旧 settings 状态查询"""
        from app.repository.user_settings_repository import get_user_settings_repository
        repo = get_user_settings_repository()
        record = await repo.get_by_session_id(session_id, db)

        if not record:
            return {
                "llm_is_configured": False,
                "llm_masked_key": None,
                "llm_base_url": None,
                "llm_model": None,
                "embedding_is_configured": False,
                "embedding_masked_key": None,
                "embedding_base_url": None,
                "embedding_model": None,
                "asr_is_configured": False,
                "asr_masked_key": None,
                "asr_base_url": None,
                "asr_model": None,
                "updated_at": None,
            }

        return {
            "llm_is_configured": record.llm_api_key_encrypted is not None,
            "llm_masked_key": (
                self._mask_key(self._decrypt(record.llm_api_key_encrypted))
                if record.llm_api_key_encrypted
                else None
            ),
            "llm_base_url": record.llm_base_url,
            "llm_model": record.llm_model,
            "embedding_is_configured": record.embedding_api_key_encrypted is not None,
            "embedding_masked_key": (
                self._mask_key(self._decrypt(record.embedding_api_key_encrypted))
                if record.embedding_api_key_encrypted
                else None
            ),
            "embedding_base_url": record.embedding_base_url,
            "embedding_model": record.embedding_model,
            "asr_is_configured": record.asr_api_key_encrypted is not None,
            "asr_masked_key": (
                self._mask_key(self._decrypt(record.asr_api_key_encrypted))
                if record.asr_api_key_encrypted
                else None
            ),
            "asr_base_url": record.asr_base_url,
            "asr_model": record.asr_model,
            "updated_at": record.updated_at,
        }

    async def get_embedding_credentials(
        self, session_id: Optional[str], db: AsyncSession
    ) -> Optional[UserCredentials]:
        """[deprecated] 获取用户 Embedding 配置"""
        if not session_id or not self._enabled:
            return None
        from app.repository.user_settings_repository import get_user_settings_repository
        repo = get_user_settings_repository()
        record = await repo.get_by_session_id(session_id, db)
        if not record or not record.embedding_api_key_encrypted:
            return None
        try:
            return UserCredentials(
                api_key=self._decrypt(record.embedding_api_key_encrypted),
                base_url=record.embedding_base_url,
                model=record.embedding_model,
            )
        except Exception as e:
            logger.error(f"[API_KEY_MANAGER] decrypt embedding key failed: {e}")
            return None

    def get_llm_key_sync(self, session_id: Optional[str]) -> Optional[UserCredentials]:
        """[deprecated] 同步获取 LLM Key — 等同于 get_default_credential_sync"""
        return self.get_default_credential_sync(session_id)

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    async def _get_cache_entry(
        self, session_id: str, db: AsyncSession
    ) -> Optional[CacheEntry]:
        """获取缓存条目（缓存未命中则查库并写入缓存）"""
        entry = await self._cache.get(session_id)
        if entry is not None:
            return entry

        # 缓存未命中，查库
        records = await self._cred_repo.list_by_session(session_id, db)
        if not records:
            # 缓存空结果防穿透
            empty_entry = CacheEntry(expire_at=time.time() + self.CACHE_TTL)
            await self._cache.set(session_id, empty_entry, self.CACHE_TTL)
            return None

        entry = CacheEntry(
            credentials={
                r.id: CredentialCacheData(
                    api_key_encrypted=r.api_key_encrypted,
                    base_url=r.base_url,
                    default_model=r.default_model,
                    provider=r.provider,
                )
                for r in records
            },
            default_credential_id=next(
                (r.id for r in records if r.is_default),
                records[0].id if records else None,  # fallback: 第一个
            ),
            expire_at=time.time() + self.CACHE_TTL,
        )
        await self._cache.set(session_id, entry, self.CACHE_TTL)
        return entry

    async def _refresh_cache(self, session_id: str, db: AsyncSession) -> None:
        """强制刷新缓存"""
        await self._cache.delete(session_id)
        records = await self._cred_repo.list_by_session(session_id, db)
        if records:
            entry = CacheEntry(
                credentials={
                    r.id: CredentialCacheData(
                        api_key_encrypted=r.api_key_encrypted,
                        base_url=r.base_url,
                        default_model=r.default_model,
                        provider=r.provider,
                    )
                    for r in records
                },
                default_credential_id=next(
                    (r.id for r in records if r.is_default), None
                ),
                expire_at=time.time() + self.CACHE_TTL,
            )
            await self._cache.set(session_id, entry, self.CACHE_TTL)

    def _encrypt(self, plaintext: str) -> str:
        """AES-256-GCM 加密 → base64(nonce + ciphertext)。若无密钥则明文 base64。"""
        if self._aesgcm is None:
            return base64.b64encode(plaintext.encode()).decode()
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def _decrypt(self, ciphertext_b64: str) -> str:
        """base64 → 解密。若无密钥则直接 base64 解码返回明文。"""
        raw = base64.b64decode(ciphertext_b64)
        if self._aesgcm is None:
            return raw.decode()
        nonce, ciphertext = raw[:12], raw[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode()

    def _mask_key(self, api_key: str) -> str:
        """隐藏 Key 中间部分，如 'sk-abc...4f2a'"""
        if len(api_key) <= 11:
            return api_key[:3] + "***" + api_key[-3:]
        return api_key[:6] + "***" + api_key[-4:]

    @property
    def is_enabled(self) -> bool:
        return self._enabled
