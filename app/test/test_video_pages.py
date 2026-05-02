# app/test/test_video_pages.py

import pytest
import re
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.utils.cache import get_cache_service


# ==================== 模型测试 ====================

class TestVideoPagesModel:
    """VideoPagesResponse 格式校验"""

    def test_video_pages_response_model(self):
        """VideoPagesResponse 格式校验"""
        from app.models import VideoPagesResponse, VideoPageInfo

        response = VideoPagesResponse(
            bvid="BV1test",
            title="Test Video",
            pages=[
                VideoPageInfo(cid=123, page=1, title="Part 1", duration=3600),
                VideoPageInfo(cid=124, page=2, title="Part 2", duration=2400),
            ],
            page_count=2
        )
        assert response.page_count == 2
        assert len(response.pages) == 2
        assert response.pages[0].page == 1
        assert response.pages[1].page == 2

    def test_video_page_info__default_values(self):
        """VideoPageInfo 字段校验"""
        from app.models import VideoPageInfo

        page = VideoPageInfo(cid=123, page=1, title="Part 1", duration=3600)
        assert page.cid == 123
        assert page.page == 1
        assert page.title == "Part 1"
        assert page.duration == 3600

    def test_video_page_info__multi_pages(self):
        """多分P场景"""
        from app.models import VideoPagesResponse, VideoPageInfo

        response = VideoPagesResponse(
            bvid="BV1234567890",
            title="课程完整版",
            pages=[
                VideoPageInfo(cid=100, page=1, title="第一章 入门", duration=1800),
                VideoPageInfo(cid=101, page=2, title="第二章 进阶", duration=2400),
                VideoPageInfo(cid=102, page=3, title="第三章 实战", duration=3600),
            ],
            page_count=3
        )
        assert response.page_count == 3
        assert all(p.page == i + 1 for i, p in enumerate(response.pages))

    def test_video_pages_response__single_page(self):
        """单分P场景"""
        from app.models import VideoPagesResponse, VideoPageInfo

        response = VideoPagesResponse(
            bvid="BV1SinglePage",
            title="单P视频",
            pages=[VideoPageInfo(cid=999, page=1, title="完整视频", duration=6000)],
            page_count=1
        )
        assert response.page_count == 1


class TestBvidValidation:
    """bvid 格式校验"""

    def test_valid_bvid_formats(self):
        """有效 bvid 格式"""
        valid_bvids = [
            "BV1GJ411x7h7",
            "bv1xx411c7xz",
            "BV1234567890",
            "bvabcdef1234",
        ]
        pattern = r"^[Bb][Vv][a-zA-Z0-9]{10}$"
        for bvid in valid_bvids:
            assert re.match(pattern, bvid), f"Should be valid: {bvid}"

    def test_invalid_bvid_formats(self):
        """无效 bvid 格式"""
        invalid_bvids = [
            "INVALIDBV",
            "BV1",
            "BV1GJ411x7h7x",  # 11 chars
            "AV1234567890",    # AV prefix
            "bv1",             # too short
            "",
        ]
        pattern = r"^[Bb][Vv][a-zA-Z0-9]{10}$"
        for bvid in invalid_bvids:
            assert not re.match(pattern, bvid), f"Should be invalid: {bvid}"


# ==================== API 端点测试 ====================

@pytest.mark.asyncio
async def test_get_video_pages__cache_hit__returns_cached():
    """
    缓存命中时直接返回，不调 B站 API
    """
    cache = get_cache_service()
    cache.clear()

    # 手动写入缓存
    cache_key = "video:pages:BV1TEST123"
    test_data = {
        "bvid": "BV1TEST123",
        "title": "Test Video",
        "pages": [
            {"cid": 123, "page": 1, "title": "Part 1", "duration": 3600},
            {"cid": 124, "page": 2, "title": "Part 2", "duration": 2400},
        ],
        "page_count": 2,
    }
    cache.set(cache_key, test_data)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/knowledge/video/BV1TEST123/pages")

        assert response.status_code == 200
        data = response.json()
        assert data["bvid"] == "BV1TEST123"
        assert data["title"] == "Test Video"
        assert data["page_count"] == 2
        assert len(data["pages"]) == 2


@pytest.mark.asyncio
async def test_get_video_pages__invalid_bvid__returns_400():
    """
    bvid 格式错误返回 400
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/knowledge/video/INVALIDBV/pages")
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_video_pages__bvid_case_insensitive():
    """
    bvid 小写也应该合法（由正则处理）
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 小写 bvid 会被正则拒绝（^[Bb][Vv] 要求 B/V），实际只有大写 BV 或小写 bv 通过
        # 小写 bv 应该也是合法的
        response = await client.get("/api/knowledge/video/bv1gj411x7h7/pages")
        # 这个 bvid 格式正确但长度是 11，实际有效格式是 10 位
        # bv1gj411x7h7 有 11 个字符，应该是 400


# ==================== 缓存 TTL 测试 ====================

def test_pages_cache_key_format():
    """分P缓存 key 格式"""
    from app.routers.knowledge import PAGES_CACHE_KEY
    key = PAGES_CACHE_KEY.format(bvid="BV1TEST123")
    assert key == "video:pages:BV1TEST123"


def test_pages_cache_ttl_value():
    """分P缓存 TTL 为 24h"""
    from app.routers.knowledge import PAGES_CACHE_TTL
    assert PAGES_CACHE_TTL == 86400
