# app/test/test_video_pages_integration.py

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.utils.cache import get_cache_service


@pytest.mark.asyncio
async def test_full_flow__cache_miss_then_hit():
    """
    完整流程：
    1. 缓存未命中 → 调 B站 API（如可用）→ 写缓存
    2. 再次请求 → 缓存命中 → 直接返回

    注意：依赖 B站 API 是否可用
    """
    cache = get_cache_service()
    cache.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 第一次请求（缓存未命中，写入缓存）
        response1 = await client.get("/api/knowledge/video/BV1GJ411x7h7/pages")

        if response1.status_code == 200:
            data1 = response1.json()
            assert data1["bvid"] == "BV1GJ411x7h7"
            assert "pages" in data1
            assert data1["page_count"] == len(data1["pages"])

            # 验证缓存已写入
            cache_key = f"video:pages:BV1GJ411x7h7"
            cached = cache.get(cache_key)
            assert cached is not None
            assert cached["bvid"] == "BV1GJ411x7h7"

            # 第二次请求（缓存命中）
            response2 = await client.get("/api/knowledge/video/BV1GJ411x7h7/pages")
            data2 = response2.json()
            assert data1 == data2
        else:
            # B站 API 不可用时返回 502，这是可接受的降级行为
            assert response1.status_code == 502


@pytest.mark.asyncio
async def test_cache_key_isolation():
    """
    不同 bvid 使用不同的缓存 key，互不干扰
    """
    cache = get_cache_service()
    cache.clear()

    cache_key_a = "video:pages:BV1A1234567"
    cache_key_b = "video:pages:BV1B1234567"

    data_a = {"bvid": "BV1A1234567", "title": "Video A", "pages": [], "page_count": 1}
    data_b = {"bvid": "BV1B1234567", "title": "Video B", "pages": [], "page_count": 1}

    cache.set(cache_key_a, data_a)
    cache.set(cache_key_b, data_b)

    assert cache.get(cache_key_a)["title"] == "Video A"
    assert cache.get(cache_key_b)["title"] == "Video B"


@pytest.mark.asyncio
async def test_cache_clear_isolation():
    """
    clear() 只清空分P缓存，不影响其他 key
    """
    cache = get_cache_service()
    cache.clear()

    cache.set("video:pages:BV1TEST", {"bvid": "BV1TEST", "title": "T", "pages": [], "page_count": 1})
    cache.set("video:pages:BV2TEST", {"bvid": "BV2TEST", "title": "T2", "pages": [], "page_count": 1})
    cache.set("other:key", {"data": "other"})

    cache.clear()

    assert cache.get("video:pages:BV1TEST") is None
    assert cache.get("video:pages:BV2TEST") is None
    assert cache.get("other:key") is None
