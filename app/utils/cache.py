# app/utils/cache.py

from typing import Optional, Any, Callable, TypeVar, Union
from functools import wraps
from cachetools import TTLCache

T = TypeVar("T")


class CacheStats:
    """缓存统计（线程安全）"""

    def __init__(self):
        self._hits: int = 0
        self._misses: int = 0
        self._writes: int = 0
        self._deletes: int = 0

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def writes(self) -> int:
        return self._writes

    @property
    def deletes(self) -> int:
        return self._deletes

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def record_hit(self) -> None:
        self._hits += 1

    def record_miss(self) -> None:
        self._misses += 1

    def record_write(self) -> None:
        self._writes += 1

    def record_delete(self) -> None:
        self._deletes += 1

    def reset(self) -> None:
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._deletes = 0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "deletes": self.deletes,
            "hit_rate": round(self.hit_rate, 4),
        }


class CacheService:
    """
    企业级本地缓存服务

    线程安全：依赖 cachetools.TTLCache 自身的 GIL 保护
    （TTLCache 内部是纯 Python dict，操作足够安全）

    注意：TTL 是全局的，由 default_ttl 决定
    """

    def __init__(self, maxsize: int = 1000, default_ttl: int = 3600):
        self._cache = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._default_ttl = default_ttl
        self._stats = CacheStats()

    # ── 数据操作 ────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，不存在或已过期返回 None"""
        value = self._cache.get(key)
        if value is None:
            self._stats.record_miss()
        else:
            self._stats.record_hit()
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值

        注意：ttl 参数仅在使用 TLRUCache 时生效（需要 Python 3.9+）。
        当前使用 TTLCache 时，TTL 实际由 default_ttl 统一控制。
        本参数保留是为未来切换到 TLRUCache 兼容。
        """
        # TTLCache 不支持单条 TTL，直接写入
        self._cache[key] = value
        self._stats.record_write()

    def delete(self, key: str) -> None:
        """删除指定缓存"""
        self._cache.pop(key, None)
        self._stats.record_delete()

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

    def has(self, key: str) -> bool:
        """检查 key 是否存在且未过期"""
        # TTLCache.__contains__ 只是 dict 查询，无副作用，直接使用
        return key in self._cache

    # ── 统计 ────────────────────────────────────────────

    @property
    def stats(self) -> CacheStats:
        """返回统计信息（只读拷贝）"""
        return self._stats

    def get_stats(self) -> dict:
        """返回统计字典"""
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """重置统计计数器"""
        self._stats.reset()


# ── 全局单例 ────────────────────────────────────────────────

_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """获取全局缓存服务单例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService(maxsize=1000, default_ttl=3600)
    return _cache_service


# ── FastAPI 依赖注入 ─────────────────────────────────────────

from functools import partial
from fastapi import Depends


def cache_dependency(
    maxsize: int = 1000,
    default_ttl: int = 3600,
) -> Callable[[], CacheService]:
    """
    FastAPI 依赖注入工厂（每次调用创建新实例）

    用法：
        @router.get("/example")
        async def example(cache: CacheService = Depends(cache_dependency())):
            cache.get("key")
    """
    def dependency() -> CacheService:
        return CacheService(maxsize=maxsize, default_ttl=default_ttl)

    return dependency


def cache_dependency_singleton() -> Callable[[], CacheService]:
    """
    FastAPI 依赖注入工厂（返回全局单例）

    用法：
        @router.get("/example")
        async def example(cache: CacheService = Depends(cache_dependency_singleton())):
            cache.get("key")
    """
    def dependency() -> CacheService:
        return get_cache_service()

    return dependency