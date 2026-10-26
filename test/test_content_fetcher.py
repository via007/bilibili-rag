import unittest
from unittest.mock import AsyncMock, Mock

from app.models import ContentSource
from app.services.content_fetcher import ContentFetcher


class ContentFetcherTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_content_merges_multi_part_asr(self):
        bili = Mock()
        bili.get_video_info = AsyncMock(
            return_value={
                "title": "多P视频",
                "desc": "视频简介",
                "duration": 120,
                "owner": {"name": "UP主", "mid": 1},
                "pages": [
                    {"cid": 101, "page": 1, "part": "第一部分"},
                    {"cid": 102, "page": 2, "part": "第二部分"},
                ],
            }
        )
        fetcher = ContentFetcher(bili, Mock())
        fetcher._try_asr = AsyncMock(
            side_effect=["第一部分内容" * 20, "第二部分内容" * 20]
        )

        content = await fetcher.fetch_content("BV1", cid=101, title="多P视频")

        self.assertEqual(content.source, ContentSource.ASR)
        self.assertIn("## P1 第一部分", content.content)
        self.assertIn("## P2 第二部分", content.content)
        self.assertEqual([segment["page"] for segment in content.segments], [1, 2])
        self.assertTrue(all("start" not in segment for segment in content.segments))
        self.assertEqual(
            [call.args for call in fetcher._try_asr.await_args_list],
            [("BV1", 101), ("BV1", 102)],
        )

    async def test_fetch_content_uses_single_page_cid_when_top_level_cid_missing(self):
        bili = Mock()
        bili.get_video_info = AsyncMock(
            return_value={
                "title": "单P视频",
                "pages": [{"cid": 101, "page": 1, "part": "正片"}],
            }
        )
        fetcher = ContentFetcher(bili, Mock())
        fetcher._try_asr = AsyncMock(return_value="正片内容" * 20)

        content = await fetcher.fetch_content("BV1")

        self.assertEqual(content.source, ContentSource.ASR)
        self.assertEqual(fetcher._try_asr.await_args.args, ("BV1", 101))

    async def test_fetch_content_preserves_timed_multi_part_asr_segments(self):
        bili = Mock()
        bili.get_video_info = AsyncMock(
            return_value={
                "title": "多P视频",
                "pages": [
                    {"cid": 101, "page": 1, "part": "第一部分"},
                    {"cid": 102, "page": 2, "part": "第二部分"},
                ],
            }
        )
        fetcher = ContentFetcher(bili, Mock())
        fetcher._try_asr = AsyncMock(side_effect=[
            {"text": "第一部分内容" * 20, "segments": [{"text": "第一句", "start": 1.2, "end": 2.4}]},
            {"text": "第二部分内容" * 20, "segments": [{"text": "第二句", "start": 5.0, "end": 7.5}]},
        ])

        content = await fetcher.fetch_content("BV1", cid=101, title="多P视频")

        self.assertEqual(
            content.segments,
            [
                {"text": "第一句", "start": 1.2, "end": 2.4, "page": 1, "part": "第一部分"},
                {"text": "第二句", "start": 5.0, "end": 7.5, "page": 2, "part": "第二部分"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
