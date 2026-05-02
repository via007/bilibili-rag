"""
test_chat_with_rewrite.py - chat.py 集成测试（含改写路由）

测试 _merge_and_deduplicate 和 _vector_search_with_rewrites 函数，
验证 Query 改写与 chat.py 的集成逻辑。

注意：此文件测试的是 chat.py 中与 Query 改写相关的部分，
不是完整的聊天接口测试（test_chat.py 已覆盖）。
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from app.services.query.types import (
    RewriteResult,
    RewriteType,
    RewrittenQuery,
    StepBackMetadata,
    SubQueryMetadata,
    CONFIDENCE_THRESHOLD,
)


class TestMergeAndDeduplicate:
    """_merge_and_deduplicate 辅助函数测试"""

    def test_deduplicate_by_bvid(self):
        """相同 bvid 只保留高分"""
        from app.routers.chat import _merge_and_deduplicate

        doc1 = Document(page_content="doc1", metadata={"bvid": "BV1", "score": 0.8})
        doc2 = Document(page_content="doc2", metadata={"bvid": "BV2", "score": 0.6})
        doc3 = Document(page_content="doc1_new", metadata={"bvid": "BV1", "score": 0.9})
        doc4 = Document(page_content="doc3", metadata={"bvid": "BV3", "score": 0.7})

        result = _merge_and_deduplicate([doc1, doc2], [doc3, doc4])

        assert len(result) == 3
        bv1_result = next(d for d in result if d.metadata.get("bvid") == "BV1")
        assert bv1_result.metadata.get("score") == 0.9  # 保留高分

    def test_single_list_no_dedup(self):
        """单路检索无去重"""
        from app.routers.chat import _merge_and_deduplicate

        doc = Document(page_content="doc1", metadata={"bvid": "BV1", "score": 0.8})
        result = _merge_and_deduplicate([doc])
        assert len(result) == 1

    def test_empty_lists(self):
        """空列表处理"""
        from app.routers.chat import _merge_and_deduplicate

        result = _merge_and_deduplicate([], [])
        assert result == []

    def test_missing_bvid_kept(self):
        """无 bvid 字段的 doc 保留"""
        from app.routers.chat import _merge_and_deduplicate

        doc1 = Document(page_content="doc1", metadata={"bvid": "BV1", "score": 0.8})
        doc2 = Document(page_content="doc2", metadata={"score": 0.9})  # 无 bvid

        result = _merge_and_deduplicate([doc1], [doc2])
        assert len(result) == 2

    def test_per_video_k_limit(self):
        """每个视频最多保留 per_video_k 个片段"""
        from app.routers.chat import _merge_and_deduplicate

        docs = [
            Document(page_content=f"chunk{i}", metadata={"bvid": "BV1", "score": 0.9 - i * 0.1})
            for i in range(5)
        ]

        result = _merge_and_deduplicate(docs, per_video_k=2)
        bv1_docs = [d for d in result if d.metadata.get("bvid") == "BV1"]
        assert len(bv1_docs) == 2

    def test_dict_like_metadata_access(self):
        """metadata 支持 dict-like 访问"""
        from app.routers.chat import _merge_and_deduplicate

        doc1 = Document(page_content="doc1", metadata={"bvid": "BV1", "score": 0.8})
        doc2 = Document(page_content="doc2", metadata={"bvid": "BV2", "score": 0.6})

        result = _merge_and_deduplicate([doc1], [doc2])
        assert len(result) == 2


class TestVectorSearchWithRewrites:
    """vector 路由的动态检索策略测试"""

    @pytest.fixture
    def mock_rag(self):
        rag = MagicMock()
        rag.search = MagicMock(
            return_value=[
                Document(page_content="result1", metadata={"bvid": "BV1", "score": 0.8})
            ]
        )
        return rag

    @pytest.fixture
    def mock_get_rag(self, mock_rag):
        with patch("app.routers.chat.get_rag_service", return_value=mock_rag):
            yield mock_rag

    @pytest.mark.asyncio
    async def test_no_rewrites_falls_back_to_direct(self, mock_get_rag):
        """无改写结果时降级为直接检索"""
        from app.routers.chat import _vector_search_with_rewrites

        rewrite_result = RewriteResult(
            original="Rust 所有权",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )

        context, docs = await _vector_search_with_rewrites(
            "Rust 所有权", rewrite_result, bvids=None, k=5
        )

        # 直接用原始 query 检索，只调用一次
        assert mock_get_rag.search.call_count == 1
        mock_get_rag.search.assert_called_once_with("Rust 所有权", k=5, bvids=None)

    @pytest.mark.asyncio
    async def test_step_back_uses_both_queries(self, mock_get_rag):
        """后退提示词策略：必须同时使用 step_back_query 和 specific_query 检索"""
        from app.routers.chat import _vector_search_with_rewrites

        stepback_rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="泛化 query",
            confidence=0.85,
            reason="test",
            metadata=StepBackMetadata(
                step_back_query="Rust 编程基础",
                specific_query="Rust 所有权规则详解",
            ),
        )
        rewrite_result = RewriteResult(
            original="Rust 所有权规则详解",
            rewrites=[stepback_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )

        # Mock 两路检索返回不同结果
        mock_get_rag.search.side_effect = [
            [Document(page_content="general", metadata={"bvid": "BV_general", "score": 0.9})],
            [Document(page_content="specific", metadata={"bvid": "BV_specific", "score": 0.8})],
        ]

        context, docs = await _vector_search_with_rewrites(
            "Rust 所有权规则详解", rewrite_result, bvids=None, k=5
        )

        # 两路并发检索
        assert mock_get_rag.search.call_count == 2
        mock_get_rag.search.assert_any_call("Rust 编程基础", k=5, bvids=None)
        mock_get_rag.search.assert_any_call("Rust 所有权规则详解", k=5, bvids=None)

    @pytest.mark.asyncio
    async def test_sub_queries_uses_all_queries(self, mock_get_rag):
        """子查询拆分策略：必须使用所有 sub_queries 并发检索"""
        from app.routers.chat import _vector_search_with_rewrites

        sub_rewrite = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="王德峰和哲学",
            confidence=0.9,
            reason="test",
            metadata=SubQueryMetadata(
                is_multi_topic=True,
                sub_queries=["王德峰", "哲学", "王德峰和哲学的关系"],
                main_topic="王德峰与哲学",
            ),
        )
        rewrite_result = RewriteResult(
            original="王德峰和哲学",
            rewrites=[sub_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )

        # Mock 三路检索返回
        mock_get_rag.search.side_effect = [
            [Document(page_content="r1", metadata={"bvid": "BV1", "score": 0.9})],
            [Document(page_content="r2", metadata={"bvid": "BV2", "score": 0.8})],
            [Document(page_content="r3", metadata={"bvid": "BV3", "score": 0.7})],
        ]

        await _vector_search_with_rewrites("王德峰和哲学", rewrite_result, bvids=None, k=5)

        # 必须并发执行 3 路检索
        assert mock_get_rag.search.call_count == 3
        mock_get_rag.search.assert_any_call("王德峰", k=5, bvids=None)
        mock_get_rag.search.assert_any_call("哲学", k=5, bvids=None)
        mock_get_rag.search.assert_any_call("王德峰和哲学的关系", k=5, bvids=None)

    @pytest.mark.asyncio
    async def test_sub_queries_not_just_first(self, mock_get_rag):
        """关键验证：sub_query 拆分不能只取 [0]，必须用所有子 query"""
        from app.routers.chat import _vector_search_with_rewrites

        sub_rewrite = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="王德峰和哲学",
            confidence=0.9,
            reason="test",
            metadata=SubQueryMetadata(
                is_multi_topic=True,
                sub_queries=["王德峰", "哲学"],
                main_topic="王德峰与哲学",
            ),
        )
        rewrite_result = RewriteResult(
            original="王德峰和哲学",
            rewrites=[sub_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )

        await _vector_search_with_rewrites("王德峰和哲学", rewrite_result, bvids=None, k=5)

        # 验证所有子 query 都被调用，不是只取 [0]
        calls = mock_get_rag.search.call_args_list
        assert mock_get_rag.search.call_count == 2  # 不能是 1

    @pytest.mark.asyncio
    async def test_confidence_below_threshold_falls_back(self, mock_get_rag):
        """置信度低于阈值时降级为直接检索"""
        from app.routers.chat import _vector_search_with_rewrites

        low_conf_rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="泛化",
            confidence=0.3,  # < 0.6
            reason="test",
            metadata=StepBackMetadata(step_back_query="泛化", specific_query="具体"),
        )
        rewrite_result = RewriteResult(
            original="test",
            rewrites=[low_conf_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )

        await _vector_search_with_rewrites("test", rewrite_result, bvids=None, k=5)

        # 降级为直接检索，只调用一次
        assert mock_get_rag.search.call_count == 1

    @pytest.mark.asyncio
    async def test_bvids_filter_passed_to_search(self, mock_get_rag):
        """bvids 过滤参数应正确传递"""
        from app.routers.chat import _vector_search_with_rewrites

        rewrite_result = RewriteResult(
            original="test",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )

        bvids_filter = ["BV1", "BV2"]

        await _vector_search_with_rewrites("test", rewrite_result, bvids=bvids_filter, k=5)

        mock_get_rag.search.assert_called_once_with("test", k=5, bvids=bvids_filter)

    @pytest.mark.asyncio
    async def test_empty_bvids_passed_as_none(self, mock_get_rag):
        """空 bvids 应传递为 None"""
        from app.routers.chat import _vector_search_with_rewrites

        rewrite_result = RewriteResult(
            original="test",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )

        await _vector_search_with_rewrites("test", rewrite_result, bvids=[], k=5)

        # 空列表应被转换为 None
        mock_get_rag.search.assert_called_once_with("test", k=5, bvids=None)

    @pytest.mark.asyncio
    async def test_returns_tuple_of_context_and_sources(self, mock_get_rag):
        """返回值应为 (context_str, sources_list) 元组"""
        from app.routers.chat import _vector_search_with_rewrites

        rewrite_result = RewriteResult(
            original="test",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )

        result = await _vector_search_with_rewrites("test", rewrite_result, bvids=None, k=5)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)  # context
        assert isinstance(result[1], list)  # sources


class TestRewriteResultInSseSourcesEvent:
    """SSE sources 事件附加改写信息测试"""

    @pytest.mark.asyncio
    async def test_sources_event_contains_rewrite_info(self):
        """sources 事件应包含 rewrite_info 字段（用于前端调试）"""
        from app.services.query.types import RewriteResult, RewriteType, RewrittenQuery
        from app.routers.chat import SSEEvent

        # 验证 SSEEvent 能正确构造包含 rewrite_info 的 sources 事件
        rewrite_result = RewriteResult(
            rewrites=[
                RewrittenQuery(
                    type=RewriteType.EXPAND,
                    query="test query",
                    confidence=0.9,
                    reasoning="test reasoning",
                )
            ],
            needs_rewrite=True,
            suggested_route="vector",
        )

        # 验证 sources 事件格式包含 rewrite_info
        sources_event = SSEEvent(
            type="sources",
            sources=[],
            rewrite_info={
                "rewrites": [
                    {
                        "type": "expand",
                        "query": "test query",
                        "confidence": 0.9,
                    }
                ],
                "needs_rewrite": True,
                "suggested_route": "vector",
            },
        )

        assert sources_event.type == "sources"
        assert sources_event.rewrite_info is not None
        assert sources_event.rewrite_info["suggested_route"] == "vector"


class TestBuildContextFromDocs:
    """_build_context_from_docs 辅助函数测试"""

    def test_empty_docs(self):
        """空文档列表"""
        from app.routers.chat import _build_context_from_docs

        context, sources = _build_context_from_docs([])
        assert context == ""
        assert sources == []

    def test_single_doc(self):
        """单文档"""
        from app.routers.chat import _build_context_from_docs

        doc = Document(
            page_content="这是视频内容",
            metadata={"bvid": "BV123", "title": "测试视频", "timestamp": 42},
        )
        context, sources = _build_context_from_docs([doc])

        assert "这是视频内容" in context
        assert len(sources) == 1
        assert sources[0]["bvid"] == "BV123"

    def test_multiple_docs_same_bvid(self):
        """同一 bvid 的多个片段去重"""
        from app.routers.chat import _build_context_from_docs

        docs = [
            Document(page_content=f"chunk{i}", metadata={"bvid": "BV1", "score": 0.9 - i * 0.1})
            for i in range(3)
        ]
        context, sources = _build_context_from_docs(docs)

        # 同一 bvid 只保留一个 source
        bvids = [s["bvid"] for s in sources]
        assert bvids.count("BV1") == 1
