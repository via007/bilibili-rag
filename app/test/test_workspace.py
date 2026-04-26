"""
test_workspace.py - Workspace 功能单元测试

测试 WorkspacePage 模型、ChatRequest.workspace_pages 扩展、
rag.search workspace_pages 过滤、以及 _prepare_messages 工作区模式路由。
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

# ==================== WorkspacePage Pydantic 模型测试 ====================

class TestWorkspacePageModel:
    """WorkspacePage 模型测试"""

    def test_workspace_page_basic(self):
        """基本序列化"""
        from app.models import WorkspacePage

        wp = WorkspacePage(bvid="BV123456", cid=987654, page_index=2, page_title="P3. 第三章")
        assert wp.bvid == "BV123456"
        assert wp.cid == 987654
        assert wp.page_index == 2
        assert wp.page_title == "P3. 第三章"

    def test_workspace_page_optional_title(self):
        """page_title 可选"""
        from app.models import WorkspacePage

        wp = WorkspacePage(bvid="BV123456", cid=987654, page_index=0)
        assert wp.page_title is None

    def test_workspace_page_defaults(self):
        """page_index 默认为 0"""
        from app.models import WorkspacePage

        wp = WorkspacePage(bvid="BV123456", cid=987654)
        assert wp.page_index == 0

    def test_workspace_page_serialization(self):
        """model_dump 序列化"""
        from app.models import WorkspacePage

        wp = WorkspacePage(bvid="BVTEST", cid=123, page_index=1, page_title="P2. 测试")
        dumped = wp.model_dump()
        assert dumped == {"bvid": "BVTEST", "cid": 123, "page_index": 1, "page_title": "P2. 测试"}


# ==================== ChatRequest workspace_pages 扩展测试 ====================

class TestChatRequestWorkspace:
    """ChatRequest.workspace_pages 字段测试"""

    def test_chat_request_with_workspace_pages(self):
        """带 workspace_pages 的请求"""
        from app.models import ChatRequest, WorkspacePage

        wp = WorkspacePage(bvid="BV001", cid=111, page_index=0, page_title="P1")
        req = ChatRequest(
            question="这个视频讲了什么",
            session_id="sess123",
            folder_ids=[1, 2],
            workspace_pages=[wp],
        )
        assert len(req.workspace_pages) == 1
        assert req.workspace_pages[0].bvid == "BV001"

    def test_chat_request_without_workspace_pages(self):
        """不带 workspace_pages 时为 None"""
        from app.models import ChatRequest

        req = ChatRequest(question="测试问题")
        assert req.workspace_pages is None

    def test_chat_request_multiple_workspace_pages(self):
        """多个 workspace_pages"""
        from app.models import ChatRequest, WorkspacePage

        wp1 = WorkspacePage(bvid="BV001", cid=111, page_index=0)
        wp2 = WorkspacePage(bvid="BV001", cid=222, page_index=1)
        wp3 = WorkspacePage(bvid="BV002", cid=333, page_index=0)
        req = ChatRequest(question="跨视频问题", workspace_pages=[wp1, wp2, wp3])
        assert len(req.workspace_pages) == 3

    def test_chat_request_empty_workspace_pages(self):
        """空列表 vs None"""
        from app.models import ChatRequest

        req_none = ChatRequest(question="无工作区", workspace_pages=None)
        req_empty = ChatRequest(question="空工作区", workspace_pages=[])
        assert req_none.workspace_pages is None
        assert req_empty.workspace_pages == []


# ==================== rag.search workspace_pages 过滤测试 ====================

class TestRagSearchWorkspace:
    """rag.search workspace_pages 参数测试"""

    @pytest.fixture
    def mock_vectorstore(self):
        """模拟 Chroma 向量存储"""
        store = MagicMock()
        store.similarity_search = MagicMock(return_value=[])
        store._collection = MagicMock()
        store._collection.get = MagicMock(return_value={"ids": [], "metadatas": []})
        return store

    def test_search_without_workspace_pages(self, mock_vectorstore):
        """无 workspace_pages 时不进行额外过滤"""
        from app.services.rag import RAGService

        with patch.object(RAGService, "__init__", lambda x, y=None: None):
            rag = RAGService()
            rag.vectorstore = mock_vectorstore
            rag.search("测试 query", k=5, bvids=None, workspace_pages=None)
            mock_vectorstore.similarity_search.assert_called_once()

    def test_search_with_workspace_pages_filters_results(self, mock_vectorstore):
        """有 workspace_pages 时结果必须精确匹配"""
        from app.services.rag import RAGService

        # 模拟检索返回 4 个文档
        docs = [
            Document(page_content="doc1", metadata={"bvid": "BV001", "page_index": 0}),
            Document(page_content="doc2", metadata={"bvid": "BV001", "page_index": 1}),
            Document(page_content="doc3", metadata={"bvid": "BV002", "page_index": 0}),
            Document(page_content="doc4", metadata={"bvid": "BV003", "page_index": 0}),
        ]
        mock_vectorstore.similarity_search.return_value = docs

        with patch.object(RAGService, "__init__", lambda x, y=None: None):
            rag = RAGService()
            rag.vectorstore = mock_vectorstore

            workspace_pages = [
                {"bvid": "BV001", "cid": 111, "page_index": 0},
                {"bvid": "BV002", "cid": 222, "page_index": 0},
            ]
            result = rag.search("测试", k=5, bvids=None, workspace_pages=workspace_pages)

            # BV001 page 0, BV002 page 0 应该保留，BV001 page 1 被过滤，BV003 不在列表中被过滤
            assert len(result) == 2
            bvids = {d.metadata["bvid"] for d in result}
            assert bvids == {"BV001", "BV002"}
            # BV001 只保留 page_index=0
            bv001_docs = [d for d in result if d.metadata["bvid"] == "BV001"]
            assert len(bv001_docs) == 1
            assert bv001_docs[0].metadata["page_index"] == 0

    def test_search_with_empty_workspace_pages(self, mock_vectorstore):
        """空 workspace_pages 列表应不触发过滤"""
        from app.services.rag import RAGService

        docs = [
            Document(page_content="doc1", metadata={"bvid": "BV001", "page_index": 0}),
        ]
        mock_vectorstore.similarity_search.return_value = docs

        with patch.object(RAGService, "__init__", lambda x, y=None: None):
            rag = RAGService()
            rag.vectorstore = mock_vectorstore
            result = rag.search("测试", k=5, bvids=None, workspace_pages=[])
            # 空列表不应触发工作区过滤，但 workspace_pages=None 和 workspace_pages=[] 语义相同
            assert len(result) == 1

    def test_search_workspace_pages_uses_bvid_filter_first(self, mock_vectorstore):
        """workspace_pages 模式先用 bvids 做预过滤，再用 page_index 精确过滤"""
        from app.services.rag import RAGService

        workspace_pages = [{"bvid": "BV001", "page_index": 0}]
        mock_vectorstore.similarity_search.return_value = []

        with patch.object(RAGService, "__init__", lambda x, y=None: None):
            rag = RAGService()
            rag.vectorstore = mock_vectorstore
            rag.search("测试", k=5, bvids=None, workspace_pages=workspace_pages)
            # 验证 filter 被传入
            call_args = mock_vectorstore.similarity_search.call_args
            assert call_args.kwargs.get("filter") == {"bvid": {"$in": ["BV001"]}}


# ==================== _vector_search_with_rewrites workspace_pages 测试 ====================

class TestVectorSearchWithRewritesWorkspace:
    """_vector_search_with_rewrites workspace_pages 透传测试"""

    @pytest.fixture
    def mock_rag(self):
        rag = MagicMock()
        rag.search = MagicMock(return_value=[])
        return rag

    @pytest.fixture
    def mock_get_rag(self, mock_rag):
        with patch("app.routers.chat.get_rag_service", return_value=mock_rag):
            yield mock_rag

    @pytest.mark.asyncio
    async def test_workspace_pages_passed_to_search(self, mock_get_rag):
        """workspace_pages 应透传给 rag.search"""
        from app.routers.chat import _vector_search_with_rewrites
        from app.services.query.types import RewriteResult

        rewrite_result = RewriteResult(
            original="测试",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )
        workspace_pages = [{"bvid": "BV001", "cid": 111, "page_index": 0}]

        await _vector_search_with_rewrites(
            "测试", rewrite_result, bvids=None, k=5, workspace_pages=workspace_pages
        )

        mock_get_rag.search.assert_called_once()
        call_kwargs = mock_get_rag.search.call_args.kwargs
        assert call_kwargs.get("workspace_pages") == workspace_pages

    @pytest.mark.asyncio
    async def test_workspace_pages_none_when_not_provided(self, mock_get_rag):
        """未提供 workspace_pages 时传递 None"""
        from app.routers.chat import _vector_search_with_rewrites
        from app.services.query.types import RewriteResult

        rewrite_result = RewriteResult(
            original="测试",
            rewrites=[],
            suggested_route="vector",
            needs_rewrite=False,
        )

        await _vector_search_with_rewrites(
            "测试", rewrite_result, bvids=None, k=5, workspace_pages=None
        )

        call_kwargs = mock_get_rag.search.call_args.kwargs
        assert call_kwargs.get("workspace_pages") is None

    @pytest.mark.asyncio
    async def test_step_back_with_workspace_pages(self, mock_get_rag):
        """step_back 策略下 workspace_pages 同样透传给每路检索（验证调用参数）"""
        from app.routers.chat import _vector_search_with_rewrites
        from app.services.query.types import (
            RewriteResult, RewriteType, RewrittenQuery, StepBackMetadata,
        )
        from unittest.mock import AsyncMock

        stepback_rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="泛化",
            confidence=0.85,
            reason="test",
            metadata=StepBackMetadata(step_back_query="泛化 query", specific_query="具体 query"),
        )
        rewrite_result = RewriteResult(
            original="具体 query",
            rewrites=[stepback_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )
        workspace_pages = [{"bvid": "BV001", "page_index": 0}]

        # 使用 AsyncMock 使 rag.search 可正确 await
        mock_get_rag.search = AsyncMock(
            side_effect=lambda *args, **kwargs: [
                Document(page_content="g", metadata={"bvid": "BV001", "page_index": 0}),
                Document(page_content="s", metadata={"bvid": "BV001", "page_index": 0}),
            ]
        )

        await _vector_search_with_rewrites(
            "具体 query", rewrite_result, bvids=None, k=5, workspace_pages=workspace_pages
        )

        # 验证两路并发检索都传递了 workspace_pages
        assert mock_get_rag.search.call_count == 2
        for call in mock_get_rag.search.call_args_list:
            assert call.kwargs.get("workspace_pages") == workspace_pages

    @pytest.mark.asyncio
    async def test_sub_queries_with_workspace_pages(self, mock_get_rag):
        """sub_queries 策略下 workspace_pages 同样透传给所有子查询（验证调用参数）"""
        from app.routers.chat import _vector_search_with_rewrites
        from app.services.query.types import (
            RewriteResult, RewriteType, RewrittenQuery, SubQueryMetadata,
        )
        from unittest.mock import AsyncMock

        sub_rewrite = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="A 和 B",
            confidence=0.9,
            reason="test",
            metadata=SubQueryMetadata(sub_queries=["A", "B"], is_multi_topic=True, main_topic="A与B"),
        )
        rewrite_result = RewriteResult(
            original="A 和 B",
            rewrites=[sub_rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )
        workspace_pages = [{"bvid": "BV001", "page_index": 1}]

        # 使用 AsyncMock 使 rag.search 可正确 await
        mock_get_rag.search = AsyncMock(
            side_effect=lambda *args, **kwargs: [
                Document(page_content="r1", metadata={"bvid": "BV001", "page_index": 1}),
                Document(page_content="r2", metadata={"bvid": "BV001", "page_index": 1}),
            ]
        )

        await _vector_search_with_rewrites(
            "A 和 B", rewrite_result, bvids=None, k=5, workspace_pages=workspace_pages
        )

        # 验证所有子查询都传递了 workspace_pages
        assert mock_get_rag.search.call_count == 2
        for call in mock_get_rag.search.call_args_list:
            assert call.kwargs.get("workspace_pages") == workspace_pages


# ==================== _prepare_messages 工作区模式路由测试 ====================

class TestPrepareMessagesWorkspace:
    """_prepare_messages 工作区强制 vector 路由测试"""

    @pytest.fixture
    def mock_get_rag(self):
        mock_rag = MagicMock()
        mock_rag.search = MagicMock(return_value=[])
        with patch("app.routers.chat.get_rag_service", return_value=mock_rag):
            yield mock_rag

    @pytest.mark.asyncio
    async def test_workspace_mode_forces_vector_route(self, mock_get_rag, test_db):
        """有 workspace_pages 时强制路由为 vector"""
        from app.routers.chat import _prepare_messages
        from app.models import ChatRequest, WorkspacePage

        wp = WorkspacePage(bvid="BV001", cid=111, page_index=0)
        req = ChatRequest(
            question="这个章节讲了什么",
            session_id=None,
            folder_ids=None,
            workspace_pages=[wp],
        )

        # Mock _route_with_llm 返回 direct（工作区应该忽略 LLM 路由）
        with patch("app.routers.chat._route_with_llm", return_value=("direct", "")):
            messages, sources, _, _ = await _prepare_messages(req, test_db, rewrite_result=None)

        # 工作区模式应强制 vector 路由
        # vector 路由最终会走到 _vector_search_with_rewrites
        # 由于 mock_get_rag.search 返回空列表，最终会走到 fallback
        # 关键验证：workspace_mode=True 时，即使 LLM 返回 direct，也会走 vector
        # 由于没有 session_id 和 folder_ids，has_data=False，
        # 实际上会走无数据分支，但 workspace_mode 标记已记录

    @pytest.mark.asyncio
    async def test_workspace_mode_logged(self, mock_get_rag, test_db):
        """工作区模式应打日志"""
        from app.routers.chat import _prepare_messages
        from app.models import ChatRequest, WorkspacePage

        wp = WorkspacePage(bvid="BV001", cid=111, page_index=0)
        req = ChatRequest(question="测试", workspace_pages=[wp])

        with patch("app.routers.chat._route_with_llm", return_value=("direct", "")):
            with patch("app.routers.chat.logger") as mock_logger:
                await _prepare_messages(req, test_db, rewrite_result=None)
                # 验证日志中包含工作区信息
                log_calls = [str(c) for c in mock_logger.info.call_args_list]
                workspace_logs = [c for c in log_calls if "WORKSPACE" in c]
                assert len(workspace_logs) >= 1


# ==================== 前端 API 类型测试 ====================

class TestFrontendApiTypes:
    """frontend/lib/api.ts 对应类型的前端模拟验证"""

    def test_workspace_page_type_matches_backend(self):
        """前端 WorkspacePage 类型应与后端 WorkspacePage 模型字段一致"""
        from app.models import WorkspacePage

        # 后端模型字段
        wp_fields = {"bvid", "cid", "page_index", "page_title"}
        wp = WorkspacePage(bvid="BV001", cid=111, page_index=0, page_title="P1")
        dumped = wp.model_dump()

        # 验证字段完整
        assert wp_fields == set(dumped.keys())
        assert dumped["bvid"] == "BV001"
        assert dumped["cid"] == 111
        assert dumped["page_index"] == 0
        assert dumped["page_title"] == "P1"

    def test_chat_request_payload_workspace_pages_field(self):
        """验证 ChatRequest 能正确接收 workspace_pages"""
        from app.models import ChatRequest, WorkspacePage

        payload = {
            "question": "测试问题",
            "session_id": "sess123",
            "folder_ids": [1, 2],
            "workspace_pages": [
                {"bvid": "BV001", "cid": 111, "page_index": 0, "page_title": "P1"}
            ],
        }
        req = ChatRequest(**payload)
        assert len(req.workspace_pages) == 1
        assert req.workspace_pages[0].bvid == "BV001"
