"""
test_types.py - 数据结构单元测试

覆盖 types.py 中所有数据结构和常量。
"""
import pytest
from app.services.query.types import (
    RewriteType,
    RewrittenQuery,
    RewriteResult,
    StepBackMetadata,
    SubQueryMetadata,
    CONFIDENCE_THRESHOLD,
)


class TestRewriteTypeEnum:
    """RewriteType 枚举测试"""

    def test_step_back_value(self):
        assert RewriteType.STEP_BACK.value == "step_back"

    def test_sub_queries_value(self):
        assert RewriteType.SUB_QUERIES.value == "sub_queries"

    def test_enum_membership(self):
        assert RewriteType.STEP_BACK in [RewriteType.STEP_BACK, RewriteType.SUB_QUERIES]


class TestStepBackMetadata:
    """StepBackMetadata 数据结构测试"""

    def test_creation(self):
        metadata = StepBackMetadata(
            step_back_query="Rust 编程基础",
            specific_query="Rust 所有权规则详解",
        )
        assert metadata.step_back_query == "Rust 编程基础"
        assert metadata.specific_query == "Rust 所有权规则详解"

    def test_immutable(self):
        """验证属性只读"""
        metadata = StepBackMetadata(
            step_back_query="泛化",
            specific_query="具体",
        )
        with pytest.raises(AttributeError):
            metadata.step_back_query = "new_value"


class TestSubQueryMetadata:
    """SubQueryMetadata 数据结构测试"""

    def test_creation(self):
        metadata = SubQueryMetadata(
            is_multi_topic=True,
            sub_queries=["王德峰", "哲学", "王德峰和哲学的关系"],
            main_topic="王德峰与哲学",
        )
        assert metadata.is_multi_topic is True
        assert len(metadata.sub_queries) == 3
        assert metadata.main_topic == "王德峰与哲学"

    def test_sub_queries_order_preserved(self):
        """sub_queries 顺序应与创建时一致"""
        queries = ["query1", "query2", "query3"]
        metadata = SubQueryMetadata(
            is_multi_topic=True,
            sub_queries=queries,
            main_topic="main",
        )
        assert metadata.sub_queries == queries
        assert metadata.sub_queries[0] == "query1"
        assert metadata.sub_queries[-1] == "query3"


class TestRewrittenQuery:
    """RewrittenQuery 数据结构测试"""

    def test_step_back_type_creation(self):
        metadata = StepBackMetadata(
            step_back_query="Rust 编程基础",
            specific_query="Rust 所有权规则详解",
        )
        rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="Rust 编程基础",
            confidence=0.85,
            reason="原问题过于具体",
            metadata=metadata,
        )
        assert rewrite.type == RewriteType.STEP_BACK
        assert rewrite.metadata.step_back_query == "Rust 编程基础"
        assert rewrite.metadata.specific_query == "Rust 所有权规则详解"

    def test_sub_queries_type_creation(self):
        metadata = SubQueryMetadata(
            is_multi_topic=True,
            sub_queries=["王德峰", "哲学", "王德峰和哲学的关系"],
            main_topic="王德峰与哲学",
        )
        rewrite = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="王德峰和哲学",
            confidence=0.9,
            reason="多主题查询",
            metadata=metadata,
        )
        assert rewrite.type == RewriteType.SUB_QUERIES
        assert len(rewrite.metadata.sub_queries) == 3

    def test_metadata_none_default(self):
        """metadata 默认为 None"""
        rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="test",
            confidence=0.5,
            reason="test",
        )
        assert rewrite.metadata is None

    def test_confidence_bounded(self):
        """confidence 边界值测试"""
        rewrite_low = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="test",
            confidence=0.0,
            reason="test",
        )
        assert rewrite_low.confidence == 0.0

        rewrite_high = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="test",
            confidence=1.0,
            reason="test",
        )
        assert rewrite_high.confidence == 1.0

        assert 0.0 <= rewrite_low.confidence <= 1.0
        assert 0.0 <= rewrite_high.confidence <= 1.0

    def test_all_fields_present(self):
        """所有必填字段都存在"""
        rewrite = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="test query",
            confidence=0.75,
            reason="test reason",
            metadata=None,
        )
        assert hasattr(rewrite, "type")
        assert hasattr(rewrite, "query")
        assert hasattr(rewrite, "confidence")
        assert hasattr(rewrite, "reason")
        assert hasattr(rewrite, "metadata")


class TestRewriteResult:
    """RewriteResult 数据结构测试"""

    def test_empty_rewrites(self):
        result = RewriteResult(
            original="你好",
            rewrites=[],
            suggested_route="direct",
            needs_rewrite=False,
        )
        assert result.rewrites == []
        assert result.needs_rewrite is False
        assert result.original == "你好"
        assert result.suggested_route == "direct"

    def test_single_rewrite(self):
        rewrite = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="泛化 query",
            confidence=0.85,
            reason="test",
            metadata=StepBackMetadata(
                step_back_query="泛化",
                specific_query="具体",
            ),
        )
        result = RewriteResult(
            original="原始问题",
            rewrites=[rewrite],
            suggested_route="vector",
            needs_rewrite=True,
        )
        assert len(result.rewrites) == 1
        assert result.needs_rewrite is True
        assert result.rewrites[0].type == RewriteType.STEP_BACK

    def test_multiple_rewrites(self):
        """支持多个改写结果"""
        rewrite1 = RewrittenQuery(
            type=RewriteType.STEP_BACK,
            query="泛化",
            confidence=0.9,
            reason="test1",
            metadata=StepBackMetadata(step_back_query="泛化", specific_query="具体"),
        )
        rewrite2 = RewrittenQuery(
            type=RewriteType.SUB_QUERIES,
            query="拆分",
            confidence=0.8,
            reason="test2",
            metadata=SubQueryMetadata(
                is_multi_topic=True,
                sub_queries=["a", "b"],
                main_topic="main",
            ),
        )
        result = RewriteResult(
            original="原始",
            rewrites=[rewrite1, rewrite2],
            suggested_route="vector",
            needs_rewrite=True,
        )
        assert len(result.rewrites) == 2

    def test_confidence_threshold_value(self):
        """确认阈值常量值正确"""
        assert CONFIDENCE_THRESHOLD == 0.6

    def test_suggested_route_values(self):
        """suggested_route 可以是多种值"""
        routes = ["direct", "db_list", "db_content", "vector"]
        for route in routes:
            result = RewriteResult(
                original="test",
                rewrites=[],
                suggested_route=route,
                needs_rewrite=False,
            )
            assert result.suggested_route == route
