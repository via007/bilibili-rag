import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from langchain.schema import Document
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, ChatRequest, FavoriteFolder, FavoriteVideo, VideoCache
from app.routers import chat


class AsyncChunkStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as error:
            raise StopAsyncIteration from error


class ChatStreamHelperTest(unittest.TestCase):
    def test_stream_event_is_one_unicode_ndjson_line(self):
        encoded = chat._encode_stream_event("status", message="正在检索")

        self.assertTrue(encoded.endswith("\n"))
        self.assertEqual(
            json.loads(encoded),
            {"type": "status", "message": "正在检索"},
        )

    def test_snippet_event_compacts_and_limits_preview(self):
        event = chat._build_snippet_event(
            Document(
                page_content=("片段 \n\t" * 100),
                metadata={"bvid": "BV1", "title": "测试视频"},
            )
        )

        self.assertNotIn("\n", event["preview"])
        self.assertLessEqual(len(event["preview"]), 223)
        self.assertEqual(event["url"], "https://www.bilibili.com/video/BV1")

    def test_snippet_and_answer_sources_link_to_p_and_timestamp(self):
        document = Document(
            page_content="检索到的片段内容",
            metadata={
                "bvid": "BV1",
                "title": "测试视频",
                "page": 2,
                "start_time": 91.8,
                "end_time": 105.2,
            },
        )

        snippet = chat._build_snippet_event(document)
        source = chat._source_from_document(document)

        self.assertEqual(snippet["url"], "https://www.bilibili.com/video/BV1?p=2&t=91")
        self.assertEqual(snippet["page"], 2)
        self.assertEqual(source["url"], snippet["url"])
        self.assertEqual(source["start_time"], 91.8)
        self.assertEqual(source["end_time"], 105.2)

    def test_data_inspection_error_is_user_facing(self):
        error = Exception("InternalError.Algo.DataInspectionFailed: data_inspection_failed")

        self.assertTrue(chat._is_data_inspection_error(error))
        self.assertIn("内容安全检查", chat._data_inspection_error_message())


class PrepareMessagesProgressTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_vector_retrieval_emits_scope_stats_and_snippets(self):
        async with self.session_factory() as db:
            folder = FavoriteFolder(session_id="session", media_id=1, title="folder")
            video = VideoCache(
                bvid="BV1",
                title="向量检索教程",
                description="介绍召回率优化",
                content="向量检索可以通过混合召回提升召回率",
            )
            db.add_all([folder, video])
            await db.flush()
            db.add(FavoriteVideo(folder_id=folder.id, bvid=video.bvid))
            await db.commit()

            rag = Mock()
            rag.search.return_value = [
                Document(
                    page_content="向量检索可以通过混合召回提升召回率",
                    metadata={"bvid": "BV1", "title": "向量检索教程", "chunk_index": 0},
                )
            ]
            events = []
            request = ChatRequest(
                question="向量检索如何提升召回率",
                session_id="session",
                folder_ids=[1],
            )

            with patch("app.routers.chat.get_rag_service", return_value=rag):
                await chat._prepare_messages(request, db, progress_callback=events.append)

        event_types = [event["type"] for event in events]
        self.assertIn("scope", event_types)
        self.assertIn("retrieval", event_types)
        self.assertIn("snippet", event_types)
        retrieval = next(event for event in events if event["type"] == "retrieval")
        self.assertGreaterEqual(retrieval["vector_count"], 1)
        self.assertGreaterEqual(retrieval["final_count"], 1)


class ChatStreamEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_forwards_progress_sources_tokens_and_done(self):
        @asynccontextmanager
        async def fake_db_context():
            yield object()

        async def fake_prepare(request, db, progress_callback=None):
            progress_callback(
                {
                    "type": "scope",
                    "stage": "scope",
                    "message": "已确定检索范围",
                    "folder_count": 1,
                    "video_count": 1,
                }
            )
            progress_callback(
                {
                    "type": "snippet",
                    "stage": "retrieval",
                    "title": "测试视频",
                    "preview": "相关片段",
                    "url": "https://www.bilibili.com/video/BV1",
                }
            )
            return (
                [{"role": "user", "content": request.question}],
                [{"bvid": "BV1", "title": "测试视频", "url": "https://www.bilibili.com/video/BV1"}],
                request.question,
            )

        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="测试回答"))]
        )
        create = AsyncMock(return_value=AsyncChunkStream([chunk]))
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

        with (
            patch("app.routers.chat.get_db_context", fake_db_context),
            patch("app.routers.chat._prepare_messages", fake_prepare),
            patch("app.routers.chat._get_async_llm_client", return_value=client),
        ):
            response = await chat.ask_question_stream(ChatRequest(question="测试问题"))
            events = []
            async for raw in response.body_iterator:
                text = raw.decode() if isinstance(raw, bytes) else raw
                events.append(json.loads(text))

        self.assertEqual(
            [event["type"] for event in events],
            ["status", "scope", "snippet", "sources", "status", "token", "done"],
        )
        self.assertEqual(events[-2]["content"], "测试回答")
        create.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
