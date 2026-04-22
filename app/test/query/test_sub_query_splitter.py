"""
test_sub_query_splitter.py - 子查询拆分策略单元测试

覆盖 sub_query_splitter.py 中的 SubQuerySplitterStrategy：
- 触发条件 (should_apply)
- 策略应用 (apply)
- 所有 sub_queries 都必须被返回（关键验证）
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.query.sub_query_splitter import SubQuerySplitterStrategy
from app.services.query.types import RewriteType, RewrittenQuery, SubQueryMetadata


class TestSubQuerySplitterShouldApply:
    """触发条件测试"""

    @pytest.fixture
    def strategy(self):
        return SubQuerySplitterStrategy(MagicMock())

    @pytest.mark.parametrize(
        "query",
        [
            "王德峰和哲学",
            "Rust 与 Go",
            "Python 以及 Java",
            "Rust 或者 Go",
            "vim 还是 emacs",
            "分别介绍 ABC",
        ],
    )
    def test_multi_topic_queries_applied(self, strategy, query):
        """包含并列连词的 query 应触发子查询拆分"""
        assert strategy.should_apply(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "Rust 所有权是什么",
            "如何学习 Python",
            "王德峰讲哲学",
            "你好",
            "谢谢",
        ],
    )
    def test_single_topic_queries_not_applied(self, strategy, query):
        """单一主题 query 不应触发子查询拆分（should_apply 只检查关键词）"""
        assert strategy.should_apply(query) is False


class TestSubQuerySplitterApply:
    """策略应用测试"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":["王德峰","哲学","王德峰和哲学的关系"],"main_topic":"王德峰与哲学","confidence":0.9,"reason":"包含并列连词"}'
            )
        )
        return SubQuerySplitterStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_apply_returns_sub_queries_rewrite(self, strategy):
        result = await strategy.apply("王德峰和哲学")

        assert result is not None
        assert result.type == RewriteType.SUB_QUERIES
        assert isinstance(result.metadata, SubQueryMetadata)
        assert len(result.metadata.sub_queries) == 3
        assert "王德峰" in result.metadata.sub_queries
        assert "哲学" in result.metadata.sub_queries
        assert result.metadata.main_topic == "王德峰与哲学"
        assert result.metadata.is_multi_topic is True
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_apply_returns_none_for_non_multi_topic(self):
        """LLM 判断为非多主题时返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":false,"sub_queries":[],"main_topic":"","confidence":0.5,"reason":"单一主题"}'
            )
        )
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("Rust 所有权是什么")
        assert result is None

    @pytest.mark.asyncio
    async def test_apply_returns_none_for_single_sub_query(self):
        """sub_queries 数量 < 2 时返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":["只有一个"],"main_topic":"main","confidence":0.9,"reason":"test"}'
            )
        )
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("只有一个子问题")
        assert result is None


class TestSubQuerySplitterAllSubqueriesUsed:
    """关键验证：所有 sub_queries 都必须被返回，不能只取 [0]"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":["query1","query2","query3","王德峰和哲学"],"main_topic":"main","confidence":0.9,"reason":"test"}'
            )
        )
        return SubQuerySplitterStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_all_sub_queries_returned(self, strategy):
        """metadata.sub_queries 必须包含所有拆分结果"""
        result = await strategy.apply("多主题查询")

        assert isinstance(result.metadata, SubQueryMetadata)
        sub_queries = result.metadata.sub_queries
        assert len(sub_queries) == 4
        assert "query1" in sub_queries
        assert "query2" in sub_queries
        assert "query3" in sub_queries
        assert "王德峰和哲学" in sub_queries

    @pytest.mark.asyncio
    async def test_original_query_preserved_in_last_position(self, strategy):
        """原始问题应保留在 sub_queries 中（通常在最后）"""
        result = await strategy.apply("王德峰和哲学")

        sub_queries = result.metadata.sub_queries
        assert "王德峰和哲学" in sub_queries


class TestSubQuerySplitterMetadataType:
    """metadata 类型验证测试"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":["a","b"],"main_topic":"main","confidence":0.8,"reason":"test"}'
            )
        )
        return SubQuerySplitterStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_metadata_is_sub_query_metadata(self, strategy):
        """返回的 metadata 应该是 SubQueryMetadata 类型"""
        result = await strategy.apply("test")
        assert isinstance(result.metadata, SubQueryMetadata)

    @pytest.mark.asyncio
    async def test_metadata_has_required_fields(self, strategy):
        """SubQueryMetadata 包含所有必要字段"""
        result = await strategy.apply("test")
        metadata = result.metadata
        assert hasattr(metadata, "is_multi_topic")
        assert hasattr(metadata, "sub_queries")
        assert hasattr(metadata, "main_topic")


class TestSubQuerySplitterEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self):
        """LLM 返回非法 JSON 时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="not a json"))
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("王德峰和哲学")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_sub_queries_returns_none(self):
        """sub_queries 为空列表时返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":[],"main_topic":"","confidence":0.9,"reason":"test"}'
            )
        )
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_optional_fields(self):
        """JSON 中缺少可选字段时应使用默认值"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(content='{"is_multi_topic":true,"sub_queries":["a","b"],"confidence":0.8}')
        )
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("test")
        assert result is not None
        assert result.metadata.main_topic == "test"  # 默认回退到原始 query

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self):
        """LLM 抛出异常时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(side_effect=Exception("API Error"))
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_confidence_is_float(self):
        """confidence 应为 float 类型"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"is_multi_topic":true,"sub_queries":["a","b"],"main_topic":"m","confidence":0.95,"reason":"test"}'
            )
        )
        strategy = SubQuerySplitterStrategy(mock_llm)

        result = await strategy.apply("test")
        assert isinstance(result.confidence, float)
