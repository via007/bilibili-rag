"""
test_step_back.py - 后退提示词策略单元测试

覆盖 step_back.py 中的 StepBackStrategy：
- 触发条件 (should_apply)
- 策略应用 (apply)
- JSON 解析容错
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.query.step_back import StepBackStrategy
from app.services.query.types import RewriteType, RewrittenQuery, StepBackMetadata


class TestStepBackStrategyShouldApply:
    """触发条件测试

    注意：StepBackStrategy.should_apply() 始终返回 True，
    简单 query 的过滤由 QueryRewriter._is_simple_query() 先行处理。
    """

    @pytest.fixture
    def strategy(self):
        return StepBackStrategy(MagicMock())

    @pytest.mark.parametrize(
        "query",
        [
            "你好",
            "谢谢",
            "在吗",
            "列出所有视频",
            "总结一下",
            "Rust 所有权是什么",
            "如何学习 Python",
        ],
    )
    def test_should_apply_always_true(self, strategy, query):
        """StepBackStrategy.should_apply() 对所有 query 返回 True"""
        assert strategy.should_apply(query) is True


class TestStepBackStrategyApply:
    """策略应用测试"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"step_back_query":"Rust 编程基础","specific_query":"Rust 所有权规则详解","confidence":0.85,"reason":"原问题过于具体"}'
            )
        )
        return StepBackStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_apply_returns_step_back_rewrite(self, strategy):
        result = await strategy.apply("Rust 所有权规则详解")

        assert result is not None
        assert result.type == RewriteType.STEP_BACK
        assert isinstance(result.metadata, StepBackMetadata)
        assert result.metadata.step_back_query == "Rust 编程基础"
        assert result.metadata.specific_query == "Rust 所有权规则详解"
        assert result.confidence == 0.85
        assert result.reason == "原问题过于具体"

    @pytest.mark.asyncio
    async def test_apply_returns_proper_query_field(self, strategy):
        """query 字段应为 step_back_query"""
        result = await strategy.apply("test query")
        assert result.query == "Rust 编程基础"

    @pytest.mark.asyncio
    async def test_apply_confidence_float(self, strategy):
        """confidence 应为 float 类型"""
        result = await strategy.apply("test query")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0


class TestStepBackStrategyInvalidJson:
    """LLM 返回非法 JSON 时的容错测试"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="not a json"))
        return StepBackStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self, strategy):
        """LLM 返回非法 JSON 时应返回 None，不崩溃"""
        result = await strategy.apply("Rust 所有权规则")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_json_returns_none(self, strategy):
        """LLM 返回空 JSON 时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="{}"))
        strategy = StepBackStrategy(mock_llm)

        result = await strategy.apply("test query")
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_json_returns_none(self, strategy):
        """LLM 返回部分 JSON 时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content='{"step_back_query":"only one"}'))
        strategy = StepBackStrategy(mock_llm)

        result = await strategy.apply("test query")
        assert result is None


class TestStepBackStrategyMetadataType:
    """metadata 类型验证测试"""

    @pytest.fixture
    def strategy(self):
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(
                content='{"step_back_query":"泛化","specific_query":"具体","confidence":0.9,"reason":"test"}'
            )
        )
        return StepBackStrategy(mock_llm)

    @pytest.mark.asyncio
    async def test_metadata_is_step_back_metadata(self, strategy):
        """返回的 metadata 应该是 StepBackMetadata 类型"""
        result = await strategy.apply("test")
        assert isinstance(result.metadata, StepBackMetadata)

    @pytest.mark.asyncio
    async def test_metadata_has_required_fields(self, strategy):
        """StepBackMetadata 包含所有必要字段"""
        result = await strategy.apply("test")
        metadata = result.metadata
        assert hasattr(metadata, "step_back_query")
        assert hasattr(metadata, "specific_query")


class TestStepBackStrategyEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_missing_optional_fields(self):
        """JSON 中缺少可选字段时应使用默认值"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(
            return_value=MagicMock(content='{"step_back_query":"泛化","confidence":0.8}')
        )
        strategy = StepBackStrategy(mock_llm)

        result = await strategy.apply("test query")
        assert result is not None
        assert result.metadata.specific_query == "泛化"  # 默认回退到 step_back_query
        assert result.metadata.step_back_query == "泛化"

    @pytest.mark.asyncio
    async def test_llm_returns_none_content(self):
        """LLM 返回 None content 时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=None))
        strategy = StepBackStrategy(mock_llm)

        result = await strategy.apply("test query")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self):
        """LLM 抛出异常时应返回 None"""
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(side_effect=Exception("API Error"))
        strategy = StepBackStrategy(mock_llm)

        result = await strategy.apply("test query")
        assert result is None
