"""
Query Rewriter Service

Query 改写服务：对用户 query 进行改写，提升向量检索召回质量。
"""
from app.services.query.rewriter import QueryRewriter
from app.services.query.types import (
    RewriteType,
    RewriteResult,
    RewrittenQuery,
    BaseMetadata,
    StepBackMetadata,
    SubQueryMetadata,
    MetadataType,
    CONFIDENCE_THRESHOLD,
)

__all__ = [
    "QueryRewriter",
    "RewriteType",
    "RewriteResult",
    "RewrittenQuery",
    "BaseMetadata",
    "StepBackMetadata",
    "SubQueryMetadata",
    "MetadataType",
    "CONFIDENCE_THRESHOLD",
]
