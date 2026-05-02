"""Package wrapper for legacy RAG service plus new agentic modules."""

from __future__ import annotations

from .legacy import RAGService
from .agentic import (
    AgenticAnswer,
    AgenticRAGService,
    AgenticState,
    ReasoningStep,
    get_agentic_rag_service,
)

__all__ = [
    "RAGService",
    "AgenticAnswer",
    "AgenticRAGService",
    "AgenticState",
    "ReasoningStep",
    "get_agentic_rag_service",
]
