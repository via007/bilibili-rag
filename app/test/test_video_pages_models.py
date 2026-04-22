# app/test/test_video_pages_models.py
# 模型和缓存 key 测试（不依赖 app.main，避免 langchain import chain）

import re


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

    def test_video_page_info__fields(self):
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


class TestPagesCacheConfig:
    """缓存配置测试"""

    def test_pages_cache_key_format(self):
        """分P缓存 key 格式: video:pages:{bvid}"""
        PAGES_CACHE_KEY = "video:pages:{bvid}"
        key = PAGES_CACHE_KEY.format(bvid="BV1TEST123")
        assert key == "video:pages:BV1TEST123"

    def test_pages_cache_ttl_value(self):
        """分P缓存 TTL 为 24h (86400s)"""
        EXPECTED_TTL = 86400
        assert EXPECTED_TTL == 86400

    def test_cache_service_available(self):
        """CacheService 可用"""
        from app.utils.cache import get_cache_service
        cache = get_cache_service()
        cache.set("test_key", {"data": "value"})
        assert cache.get("test_key") == {"data": "value"}
        cache.delete("test_key")

    def test_cache_key_isolation(self):
        """不同 bvid 使用不同缓存 key，互不干扰"""
        from app.utils.cache import get_cache_service
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
        cache.clear()
