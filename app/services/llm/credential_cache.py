"""
凭证缓存后端抽象接口。

本期实现：LocalMemoryCache (dict + TTL + asyncio.Lock)
后续扩展：RedisCache (aioredis)，实现相同接口即可无缝替换。
"""
import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CredentialCacheData:
    """单个 credential 的缓存数据（只存密文，遵循安全策略）"""
    api_key_encrypted: str
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    provider: str = ""


@dataclass
class CacheEntry:
    """多 credential 缓存条目"""
    credentials: dict[int, CredentialCacheData] = field(default_factory=dict)
    default_credential_id: Optional[int] = None
    expire_at: float = 0.0


class CredentialCacheBackend(ABC):
    """凭证缓存后端抽象接口。

    本期实现：LocalMemoryCache (dict + TTL)
    后续扩展：RedisCache (aioredis)，实现相同接口即可无缝替换。
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目，过期返回 None"""
        ...

    @abstractmethod
    async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
        """写入缓存，ttl 单位秒"""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除缓存"""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """清空所有缓存"""
        ...


class LocalMemoryCache(CredentialCacheBackend):
    """基于 dict 的本地内存缓存实现。

    线程安全：使用 asyncio.Lock 保护并发访问。
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._store: dict[str, CacheEntry] = {}

    async def get(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expire_at > time.time():
                return entry
            # 惰性删除过期条目
            del self._store[key]
            return None

    async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
        entry.expire_at = time.time() + ttl
        async with self._lock:
            self._store[key] = entry

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


# ═══════════════════════════════════════════════════════════
# 预留 Redis 实现（本期不实施，仅定义接口契约）
# ═══════════════════════════════════════════════════════════
#
# class RedisCache(CredentialCacheBackend):
#     """基于 Redis 的分布式缓存实现。
#
#     用法示例：
#         import aioredis
#         redis = aioredis.from_url("redis://localhost:6379/0")
#         cache = RedisCache(redis)
#         manager = ApiKeyManager(cache_backend=cache, ...)
#
#     接口方法：
#         get(key)  → redis.get(f"credential:{key}") → pickle.loads
#         set(key, entry, ttl) → redis.setex(f"credential:{key}", ttl, pickle.dumps)
#         delete(key) → redis.delete(f"credential:{key}")
#         clear() → redis.keys("credential:*") → redis.delete
#     """
#
#     def __init__(self, redis_client):
#         self._redis = redis_client
#
#     async def get(self, key: str) -> Optional[CacheEntry]:
#         import pickle
#         data = await self._redis.get(f"credential:{key}")
#         if data:
#             return pickle.loads(data)
#         return None
#
#     async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
#         import pickle
#         await self._redis.setex(
#             f"credential:{key}", ttl, pickle.dumps(entry)
#         )
#
#     async def delete(self, key: str) -> None:
#         await self._redis.delete(f"credential:{key}")
#
#     async def clear(self) -> None:
#         keys = await self._redis.keys("credential:*")
#         if keys:
#             await self._redis.delete(*keys)
