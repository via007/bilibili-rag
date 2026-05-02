"""
test_rewriter.py - QueryRewriter 主入口单元测试

覆盖 rewriter.py 中的核心逻辑：
- 简单 query 跳过
- 置信度阈值过滤
- 策略选择
- 路由推断
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.query.rewriter import QueryRewriter, CONFIDENCE_THRESHOLD
from app.services.query.types import (
    RewriteResult,
    RewriteType,
    RewrittenQuery,
    StepBackMetadata,
    SubQueryMetadata,
)


class TestQueryRewriterSimpleQuerySkip:
    """简单 query 跳过逻辑测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    @pytest.mark.parametrize(
        "query",
        [
            "你好",
            "嗨",
            "谢谢",
            "在吗",
            "你是谁",
            "hi",
            "test",
            "ok",
        ],
    )
    async def test_simple_queries_skip_rewrite(self, rewriter, query):
        """闲聊词和短 query 应跳过改写"""
        result = await rewriter.rewrite(query)
        assert result.rewrites == []
        assert result.needs_rewrite is False
        assert result.suggested_route == "direct"

    @pytest.mark.parametrize(
        "query",
        [
            "Rust 所有权规则是什么",
            "如何入门 Python 编程",
            "王德峰和哲学的关系",
        ],
    )
    async def test_normal_queries_trigger_rewrite(self, rewriter, query):
        """正常长度 query 应触发改写流程"""
        # Mock LLM 返回
        mock_response = MagicMock()
        mock_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.85,"reason":"test"}'
        rewriter.llm.invoke = MagicMock(return_value=mock_response)

        result = await rewriter.rewrite(query)
        assert result.needs_rewrite is True

    async def test_whitespace_only_query(self, rewriter):
        """仅空白字符视为简单 query"""
        result = await rewriter.rewrite("   ")
        assert result.needs_rewrite is False

    async def test_english_greeting(self, rewriter):
        """英文问候应跳过"""
        result = await rewriter.rewrite("hello")
        assert result.needs_rewrite is False

    async def test_very_short_query(self, rewriter):
        """少于5字符的 query 跳过"""
        result = await rewriter.rewrite("ab")
        assert result.needs_rewrite is False

    async def test_exactly_five_chars(self, rewriter):
        """恰好5字符且非闲聊词应触发改写"""
        mock_response = MagicMock()
        mock_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.85,"reason":"test"}'
        rewriter.llm.invoke = MagicMock(return_value=mock_response)

        result = await rewriter.rewrite("abcde")
        assert result.needs_rewrite is True


class TestQueryRewriterConfidenceThreshold:
    """置信度阈值过滤测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    async def test_confidence_below_threshold_skipped(self, rewriter):
        """置信度低于 0.6 的改写结果应被忽略，降级为直接检索"""
        mock_response = MagicMock()
        mock_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.4,"reason":"test"}'
        rewriter.llm.invoke = MagicMock(return_value=mock_response)

        result = await rewriter.rewrite("一个正常长度的 query")
        assert result.rewrites == []
        assert result.needs_rewrite is False

    async def test_confidence_at_threshold_accepted(self, rewriter):
        """置信度恰好等于 0.6 应被接受"""
        mock_response = MagicMock()
        mock_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.6,"reason":"test"}'
        rewriter.llm.invoke = MagicMock(return_value=mock_response)

        result = await rewriter.rewrite("一个正常长度的 query")
        assert len(result.rewrites) == 1
        assert result.rewrites[0].confidence == 0.6
        assert result.needs_rewrite is True

    async def test_confidence_above_threshold_accepted(self, rewriter):
        """置信度高于 0.6 应被接受"""
        mock_response = MagicMock()
        mock_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.95,"reason":"test"}'
        rewriter.llm.invoke = MagicMock(return_value=mock_response)

        result = await rewriter.rewrite("一个正常长度的 query")
        assert len(result.rewrites) == 1


class TestQueryRewriterStrategySelection:
    """策略选择逻辑测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    async def test_first_applicable_strategy_returned(self, rewriter):
        """应只返回第一个适用的策略，不尝试后续策略"""
        stepback_response = MagicMock()
        stepback_response.content = '{"step_back_query":"泛化","specific_query":"具体","confidence":0.9,"reason":"test"}'

        subquery_response = MagicMock()
        subquery_response.content = '{"is_multi_topic":true,"sub_queries":["a","b"],"main_topic":"main","confidence":0.9,"reason":"test"}'

        # 第一策略返回结果，第二策略不应被调用
        rewriter.llm.invoke = MagicMock(return_value=stepback_response)

        result = await rewriter.rewrite("王德峰和哲学")

        # StepBack 被调用
        assert result.rewrites[0].type == RewriteType.STEP_BACK
        # LLM 只被调用一次（第一个策略就返回了）
        assert rewriter.llm.invoke.call_count == 1

    async def test_no_applicable_strategy(self, rewriter):
        """无适用策略时返回空 rewrites"""
        # 所有策略的 should_apply 都返回 False
        for strategy in rewriter.strategies:
            strategy.should_apply = MagicMock(return_value=False)

        result = await rewriter.rewrite("王德峰和哲学")

        assert result.rewrites == []
        assert result.needs_rewrite is False

    async def test_llm_parse_failure_falls_back(self, rewriter):
        """LLM 返回非法 JSON 时降级为直接检索"""
        rewriter.llm.invoke = MagicMock(return_value=MagicMock(content="not a json"))

        result = await rewriter.rewrite("一个正常长度的 query")
        assert result.rewrites == []
        assert result.needs_rewrite is False


class TestQueryRewriterInferRoute:
    """路由推断测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    @pytest.mark.parametrize(
        "query,expected_route",
        [
            ("你好吗", "direct"),
            ("有哪些 Rust 视频", "db_list"),
            ("总结一下 Python", "db_content"),
            ("Rust 所有权是什么", "vector"),
        ],
    )
    async def test_route_inference(self, rewriter, query, expected_route):
        result = await rewriter.rewrite(query)
        assert result.suggested_route == expected_route


class TestQueryRewriterIsSimpleQuery:
    """_is_simple_query 辅助方法测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    def test_general_terms(self, rewriter):
        """闲聊词应被识别为简单 query"""
        terms = ["你好", "嗨", "哈喽", "谢谢", "在吗", "你是谁"]
        for term in terms:
            assert rewriter._is_simple_query(term) is True, f"'{term}' should be simple"

    def test_short_length(self, rewriter):
        """长度小于5应被识别为简单 query"""
        assert rewriter._is_simple_query("ab") is True
        assert rewriter._is_simple_query("abc") is True
        assert rewriter._is_simple_query("abcd") is True

    def test_normal_length_not_general(self, rewriter):
        """正常长度且非闲聊词不是简单 query"""
        assert rewriter._is_simple_query("Rust 所有权规则是什么") is False

    def test_whitespace_handling(self, rewriter):
        """空白字符处理"""
        assert rewriter._is_simple_query("   ") is True
        assert rewriter._is_simple_query("  hi  ") is True


class TestQueryRewriterRouteInference:
    """路由推断辅助方法测试"""

    @pytest.fixture
    def rewriter(self):
        with patch("langchain_openai.ChatOpenAI"):
            return QueryRewriter()

    def test_direct_route_general_question(self, rewriter):
        """通用闲聊问题"""
        result = rewriter._infer_route("你好")
        assert result == "direct"

    def test_db_list_route(self, rewriter):
        """列表类问题"""
        result = rewriter._infer_route("有哪些 Rust 视频")
        assert result == "db_list"

    def test_db_content_route(self, rewriter):
        """总结类问题"""
        result = rewriter._infer_route("总结一下 Python")
        assert result == "db_content"

    def test_vector_route_default(self, rewriter):
        """普通问题默认 vector"""
        result = rewriter._infer_route("Rust 所有权是什么")
        assert result == "vector"


class TestQueryRewriterClose:
    """close 方法测试"""

    async def test_close_does_not_raise(self):
        """close 方法应正常执行不抛异常"""
        with patch("langchain_openai.ChatOpenAI"):
            rewriter = QueryRewriter()
            await rewriter.close()  # 不应抛异常
