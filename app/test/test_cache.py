# app/test/test_cache.py

import pytest
import time
from app.utils.cache import (
    CacheService,
    CacheStats,
    get_cache_service,
    cache_dependency,
    cache_dependency_singleton,
)


class TestCacheStats:
    """CacheStats 统计类测试"""

    def test_stats_initial(self):
        """初始状态全是 0"""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.writes == 0
        assert stats.hit_rate == 0.0

    def test_record_hit(self):
        """记录命中"""
        stats = CacheStats()
        stats.record_hit()
        assert stats.hits == 1
        assert stats.hit_rate == 1.0

    def test_record_miss(self):
        """记录未命中"""
        stats = CacheStats()
        stats.record_miss()
        assert stats.misses == 1

    def test_hit_rate_calculation(self):
        """命中率计算"""
        stats = CacheStats()
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()
        assert stats.hit_rate == 2 / 3

    def test_hit_rate_no_divide_by_zero(self):
        """无请求时命中率返回 0"""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_reset(self):
        """重置统计"""
        stats = CacheStats()
        stats.record_hit()
        stats.record_write()
        stats.reset()
        assert stats.hits == 0
        assert stats.writes == 0

    def test_to_dict(self):
        """字典格式输出"""
        stats = CacheStats()
        stats.record_hit()
        stats.record_write()
        d = stats.to_dict()
        assert d["hits"] == 1
        assert d["writes"] == 1
        assert "hit_rate" in d


class TestCacheService:
    """CacheService 缓存服务测试"""

    @pytest.fixture
    def cache(self):
        """创建独立缓存实例用于测试"""
        return CacheService(maxsize=100, default_ttl=10)  # TTL=10秒用于测试

    def test_get_set(self, cache):
        """基本 get/set 操作"""
        cache.set("key1", {"data": "value1"})
        assert cache.get("key1") == {"data": "value1"}

    def test_get_nonexistent(self, cache):
        """获取不存在的 key 返回 None"""
        assert cache.get("nonexistent") is None

    def test_delete(self, cache):
        """删除缓存"""
        cache.set("key2", "value2")
        cache.delete("key2")
        assert cache.get("key2") is None

    def test_delete_nonexistent(self, cache):
        """删除不存在的 key 不报错"""
        cache.delete("nonexistent")  # 不应抛出异常

    def test_overwrite(self, cache):
        """覆盖已有缓存"""
        cache.set("key3", "value3a")
        cache.set("key3", "value3b")
        assert cache.get("key3") == "value3b"

    def test_clear(self, cache):
        """清空所有缓存"""
        cache.set("key4", "value4")
        cache.set("key5", "value5")
        cache.clear()
        assert cache.get("key4") is None
        assert cache.get("key5") is None

    def test_has(self, cache):
        """has 方法检查 key 是否存在"""
        cache.set("key6", "value6")
        assert cache.has("key6") is True
        assert cache.has("nonexistent") is False

    def test_ttl_expired(self, cache):
        """TTL 过期后缓存自动清除"""
        cache.set("key7", "value7")
        assert cache.get("key7") == "value7"
        time.sleep(11)  # 等待过期（TTL=10秒）
        assert cache.get("key7") is None

    def test_lru_eviction(self):
        """超出容量时 LRU 淘汰"""
        small_cache = CacheService(maxsize=3, default_ttl=3600)
        small_cache.set("a", "1")
        small_cache.set("b", "2")
        small_cache.set("c", "3")
        small_cache.set("d", "4")  # 触发淘汰

        # 最老的 'a' 应该被淘汰
        assert small_cache.get("a") is None
        assert small_cache.get("d") == "4"

    def test_stats_on_get(self, cache):
        """get 操作更新统计"""
        cache.set("skey1", "value")
        cache.get("nonexistent")  # miss
        cache.get("skey1")  # hit
        stats = cache.stats
        assert stats.hits == 1
        assert stats.misses == 1

    def test_stats_on_set(self, cache):
        """set 操作更新统计"""
        cache.set("skey2", "value")
        stats = cache.stats
        assert stats.writes == 1

    def test_stats_on_delete(self, cache):
        """delete 操作更新统计"""
        cache.set("skey3", "value")
        cache.delete("skey3")
        stats = cache.stats
        assert stats.deletes == 1

    def test_get_stats_dict(self, cache):
        """get_stats 返回字典"""
        cache.set("tkey1", "value")
        cache.get("tkey1")
        d = cache.get_stats()
        assert "hits" in d
        assert "writes" in d
        assert "hit_rate" in d

    def test_reset_stats(self, cache):
        """重置统计"""
        cache.set("rkey1", "value")
        cache.get("rkey1")
        cache.reset_stats()
        stats = cache.stats
        assert stats.hits == 0
        assert stats.writes == 0


class TestCacheDependency:
    """依赖注入工厂函数测试"""

    def test_cache_dependency_creates_instance(self):
        """cache_dependency 创建新实例"""
        factory = cache_dependency(maxsize=50, default_ttl=100)
        cache = factory()
        assert isinstance(cache, CacheService)
        assert cache._cache.maxsize == 50
        assert cache._default_ttl == 100

    def test_cache_dependency_different_instances(self):
        """每次调用创建不同实例"""
        factory = cache_dependency()
        cache1 = factory()
        cache2 = factory()
        assert cache1 is not cache2

    def test_cache_dependency_singleton(self):
        """cache_dependency_singleton 返回全局单例"""
        factory = cache_dependency_singleton()
        cache = factory()
        assert cache is get_cache_service()

    def test_singleton_consistency(self):
        """全局单例一致性"""
        cache1 = get_cache_service()
        cache2 = get_cache_service()
        assert cache1 is cache2
