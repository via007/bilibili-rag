"""
Query Rewriter - Type Definitions

核心数据类型定义，包含类型分层建模的 metadata 结构。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


class RewriteType(Enum):
    """改写类型枚举"""
    STEP_BACK = "step_back"       # 后退提示词（泛化）
    SUB_QUERIES = "sub_queries"  # 子查询拆分


# === metadata 类型分层建模 ===

@dataclass(frozen=True)
class BaseMetadata:
    """metadata 抽象基类"""
    pass


@dataclass(frozen=True)
class StepBackMetadata(BaseMetadata):
    """后退提示词 metadata"""
    step_back_query: str  # 泛化后的高层次问题
    specific_query: str  # 补全主语/宾语后的具体问题


@dataclass(frozen=True)
class SubQueryMetadata(BaseMetadata):
    """子查询拆分 metadata"""
    is_multi_topic: bool       # 是否多主题
    sub_queries: List[str]  # 拆分后的子 query 列表
    main_topic: str          # 主要主题


# 联合类型 - IDE 自动提示 + 避免 key 写错
MetadataType = Union[StepBackMetadata, SubQueryMetadata]


@dataclass
class RewrittenQuery:
    """单条改写结果"""
    type: RewriteType                     # 改写类型
    query: str                            # 改写后的 query 内容
    confidence: float                     # 置信度 0.0 ~ 1.0
    reason: str                           # 改写原因说明
    metadata: Optional[MetadataType] = None  # 类型安全的 metadata


# 置信度阈值（低于此值的改写结果将被忽略，降级为直接检索）
CONFIDENCE_THRESHOLD = 0.6


@dataclass
class RewriteResult:
    """QueryRewriter 返回的完整改写结果"""
    original: str                   # 用户原始 query
    rewrites: List[RewrittenQuery]  # 改写结果列表，按 confidence 降序
    suggested_route: str            # 建议路由："direct" | "db_list" | "db_content" | "vector"
    needs_rewrite: bool           # 是否需要改写（简单 query 可跳过）


# ---------------------------------------------------------------------------
# LangChain Structured Output 专用 Pydantic 模型
# ---------------------------------------------------------------------------

class StepBackStructuredOutput(BaseModel):
    """后退提示词策略的 LLM 结构化输出"""
    step_back_query: str = Field(
        description="保留核心实体和关键限定词的高层次抽象问题"
    )
    specific_query: str = Field(
        description="补全主语/宾语后的完整具体问题（禁止引入原问题不存在的信息）"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="改写置信度，0.0~1.0"
    )
    reason: str = Field(
        description="一句话说明改写策略和保留的核心实体"
    )


class SubQueryStructuredOutput(BaseModel):
    """子查询拆分策略的 LLM 结构化输出"""
    is_multi_topic: bool = Field(
        description="是否包含多个独立子主题"
    )
    sub_queries: List[str] = Field(
        description="拆分后的子 query 列表，至少2个，每个必须是完整语义，禁止单字/双字"
    )
    main_topic: str = Field(
        description="主要主题"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="拆分置信度，0.0~1.0"
    )
    reason: str = Field(
        description="拆分原因"
    )
