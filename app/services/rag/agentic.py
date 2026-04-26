from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from loguru import logger
from pydantic import BaseModel, Field

from app.config import settings
from app.services.query import (
    CONFIDENCE_THRESHOLD,
    QueryRewriter,
    RewriteResult,
    RewriteType,
    StepBackMetadata,
    SubQueryMetadata,
)
from app.services.rag.prompts import (
    agentic_draft_system_prompt,
    agentic_reflection_system_prompt,
    agentic_synthesis_system_prompt,
)

try:
    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except ImportError:
    END = "__end__"
    StateGraph = None
    HAS_LANGGRAPH = False

from . import RAGService


class ReasoningStep(BaseModel):
    step: int
    action: str
    query: str = ""
    reasoning: str = ""
    verdict: Optional[str] = None
    recall_score: Optional[float] = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    content_preview: str = ""


class AgenticAnswer(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    reasoning_steps: list[ReasoningStep]
    synthesis_method: str
    hops_used: int
    avg_recall_score: float = 0.0


class AgenticState(BaseModel):
    question: str
    bvids: list[str] = Field(default_factory=list)
    workspace_pages: Optional[list[dict[str, Any]]] = None
    k: int = 5
    max_hops: int = 3
    candidate_queries: list[str] = Field(default_factory=list)
    current_context: str = ""
    all_sources: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_steps: list[ReasoningStep] = Field(default_factory=list)
    recall_scores: list[float] = Field(default_factory=list)
    hop: int = 0
    verdict: str = "insufficient"
    answer: str = ""
    seen_chunk_ids: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgenticState:
        return cls.model_validate(data)


def _extract_keywords(text: str) -> list[str]:
    stopwords = {
        "什么",
        "怎么",
        "如何",
        "是否",
        "可以",
        "哪个",
        "哪些",
        "请问",
        "一下",
        "为什么",
        "总结",
        "介绍",
        "内容",
        "视频",
    }
    keywords: list[str] = []
    for kw in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if kw not in stopwords and kw not in keywords:
            keywords.append(kw)
    for kw in re.findall(r"[A-Za-z0-9]{2,}", text):
        if kw not in keywords:
            keywords.append(kw)
    return keywords


def _merge_sources(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {item.get("bvid") for item in existing}
    merged = list(existing)
    for item in new:
        bvid = item.get("bvid")
        if bvid and bvid not in seen:
            seen.add(bvid)
            merged.append(item)
    return merged


def _build_context_and_sources(docs: list[Document]) -> tuple[str, list[dict[str, Any]]]:
    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    seen_bvids: set[str] = set()

    for doc in docs:
        meta = doc.metadata or {}
        title = meta.get("title", "未知标题")
        bvid = meta.get("bvid", "")
        content = (doc.page_content or "").strip()
        if content:
            context_parts.append(f"【{title}】\n{content}")
        if bvid and bvid not in seen_bvids:
            seen_bvids.add(bvid)
            sources.append(
                {
                    "bvid": bvid,
                    "title": title,
                    "url": meta.get("url", f"https://www.bilibili.com/video/{bvid}"),
                }
            )

    return "\n\n---\n\n".join(context_parts), sources


def _chunk_id_for_doc(doc: Document) -> str:
    meta = doc.metadata or {}
    return f"{meta.get('bvid', '')}:{meta.get('page_index', 0)}:{meta.get('chunk_index', 0)}"


def _calculate_recall_score(
    docs: list[Document],
    question: str,
    similarity_scores: Optional[list[float]] = None,
) -> float:
    if not docs:
        return 0.0

    unique_bvids = len({doc.metadata.get("bvid", "") for doc in docs if doc.metadata.get("bvid")})
    diversity = unique_bvids / max(len(docs), 1)

    if similarity_scores:
        # Chroma 默认返回 L2 距离，越小越相似；映射到 [0, 1]
        similarities = [1.0 / (1.0 + score) for score in similarity_scores]
        avg_similarity = sum(similarities) / len(similarities)
        score = 0.6 * avg_similarity + 0.4 * diversity
    else:
        keywords = _extract_keywords(question)
        if not keywords:
            return 1.0
        relevance_scores: list[float] = []
        for doc in docs:
            haystack = f"{doc.metadata.get('title', '')}\n{doc.page_content}".lower()
            matched = sum(1 for kw in keywords if kw.lower() in haystack)
            relevance_scores.append(matched / max(len(keywords), 1))
        score = 0.4 + 0.4 * (sum(relevance_scores) / len(relevance_scores)) + 0.2 * diversity

    return round(min(score, 1.0), 3)


def _preview_context(text: str, limit: int = 240) -> str:
    preview = " ".join(text.split())
    return preview[:limit]


class AgenticRAGService:
    def __init__(
        self,
        rag_service: RAGService,
        rewriter: Optional[QueryRewriter] = None,
    ):
        self.rag = rag_service
        self.rewriter = rewriter or QueryRewriter()
        self.graph = self._build_graph() if HAS_LANGGRAPH else None

    def _build_candidate_queries(self, question: str, rewrite_result: Optional[RewriteResult]) -> list[str]:
        queries: list[str] = [question]
        if not rewrite_result:
            return queries

        for rewrite in rewrite_result.rewrites:
            if rewrite.confidence < CONFIDENCE_THRESHOLD:
                continue
            metadata = rewrite.metadata
            if rewrite.type == RewriteType.STEP_BACK and isinstance(metadata, StepBackMetadata):
                queries.extend([metadata.step_back_query, metadata.specific_query])
            elif rewrite.type == RewriteType.SUB_QUERIES and isinstance(metadata, SubQueryMetadata):
                queries.extend(metadata.sub_queries)
            if rewrite.query:
                queries.append(rewrite.query)

        unique_queries: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = (query or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                unique_queries.append(cleaned)
        return unique_queries

    def _build_graph(self):
        graph = StateGraph(dict)
        graph.add_node("search", self._graph_search_node)
        graph.add_node("reflect", self._graph_reflect_node)
        graph.add_node("synthesize", self._graph_synthesize_node)
        graph.set_entry_point("search")
        graph.add_edge("search", "reflect")
        graph.add_conditional_edges("reflect", self._graph_next_step, {"search": "search", "synthesize": "synthesize"})
        graph.add_edge("synthesize", END)
        return graph.compile()

    async def _graph_search_node(self, state: dict[str, Any]) -> dict[str, Any]:
        agentic_state = AgenticState.from_dict(state)
        await self._run_search_hop(agentic_state)
        return agentic_state.to_dict()

    async def _graph_reflect_node(self, state: dict[str, Any]) -> dict[str, Any]:
        agentic_state = AgenticState.from_dict(state)
        await self._run_reflection(agentic_state)
        return agentic_state.to_dict()

    async def _graph_synthesize_node(self, state: dict[str, Any]) -> dict[str, Any]:
        agentic_state = AgenticState.from_dict(state)
        await self._run_synthesis(agentic_state)
        return agentic_state.to_dict()

    def _graph_next_step(self, state: dict[str, Any]) -> str:
        hop = int(state.get("hop", 0))
        max_hops = int(state.get("max_hops", 0))
        verdict = state.get("verdict", "insufficient")
        if verdict == "sufficient" or hop >= max_hops:
            return "synthesize"
        return "search"

    async def _run_search_hop(self, state: AgenticState) -> None:
        if state.hop >= state.max_hops:
            return

        query_index = min(state.hop, max(len(state.candidate_queries) - 1, 0))
        query = state.candidate_queries[query_index] if state.candidate_queries else state.question

        # 构建 filter 条件（与 RAGService.search 保持一致）
        filter_cond = None
        if state.workspace_pages:
            wp_bvids = list(set(wp.get("bvid") for wp in state.workspace_pages))
            filter_cond = {"bvid": {"$in": wp_bvids}}
        elif state.bvids:
            filter_cond = {"bvid": {"$in": state.bvids}}

        try:
            if filter_cond:
                docs_with_scores = self.rag.vectorstore.similarity_search_with_score(query, k=state.k, filter=filter_cond)
            else:
                docs_with_scores = self.rag.vectorstore.similarity_search_with_score(query, k=state.k)
        except Exception as exc:
            logger.warning(f"[AGENTIC_RAG] vector search failed: {exc}")
            docs_with_scores = []

        # 工作区模式：进一步按 page_index 精确过滤
        if state.workspace_pages:
            wp_set = {(wp.get("bvid"), wp.get("page_index", 0)) for wp in state.workspace_pages}
            docs_with_scores = [
                (d, s) for d, s in docs_with_scores
                if (d.metadata.get("bvid"), d.metadata.get("page_index", 0)) in wp_set
            ]

        # 去重：基于 chunk_id 过滤已见过的文档块
        unique_docs: list[Document] = []
        similarity_scores: list[float] = []
        for doc, score in docs_with_scores:
            cid = _chunk_id_for_doc(doc)
            if cid not in state.seen_chunk_ids:
                state.seen_chunk_ids.append(cid)
                unique_docs.append(doc)
                similarity_scores.append(score)

        if not unique_docs:
            state.hop += 1
            return

        context, sources = _build_context_and_sources(unique_docs)
        recall_score = _calculate_recall_score(unique_docs, state.question, similarity_scores)

        if context:
            state.current_context = f"{state.current_context}\n\n{context}".strip() if state.current_context else context
        state.all_sources = _merge_sources(state.all_sources, sources)
        state.recall_scores.append(recall_score)
        state.hop += 1
        state.reasoning_steps.append(
            ReasoningStep(
                step=state.hop,
                action="search",
                query=query,
                reasoning="向量检索当前问题或改写后的问题。",
                recall_score=recall_score,
                sources=sources[:3],
                content_preview=_preview_context(context),
            )
        )

    async def _build_draft_answer(self, question: str, context: str) -> str:
        if not context.strip():
            return ""
        prompt = agentic_draft_system_prompt(question, context)
        response = await self.rag.llm.ainvoke([HumanMessage(content=prompt)], config={"timeout": 30})
        return str(response.content or "").strip()

    async def _run_reflection(self, state: AgenticState) -> None:
        draft_answer = await self._build_draft_answer(state.question, state.current_context)
        state.answer = draft_answer
        prompt = agentic_reflection_system_prompt(
            state.question, draft_answer, state.current_context
        )
        response = await self.rag.llm.ainvoke([HumanMessage(content=prompt)], config={"timeout": 30})
        raw = str(response.content or "").strip()
        match = re.search(r"\b(sufficient|insufficient)\b", raw, re.IGNORECASE)
        verdict = match.group(1).lower() if match else "insufficient"
        state.verdict = verdict
        state.reasoning_steps.append(
            ReasoningStep(
                step=state.hop,
                action="reflect",
                reasoning=raw or "模型未返回反思结论。",
                verdict=verdict,
            )
        )

    async def _run_synthesis(self, state: AgenticState) -> None:
        if not state.current_context.strip():
            state.answer = "没有检索到足够的知识库内容来回答这个问题。"
            return

        prompt = agentic_synthesis_system_prompt(state.question, state.current_context)
        response = await self.rag.llm.ainvoke([HumanMessage(content=prompt)], config={"timeout": 30})
        state.answer = str(response.content or "").strip() or "没有生成有效答案。"

    async def _fallback_loop(self, state: AgenticState) -> AgenticState:
        while state.hop < state.max_hops:
            await self._run_search_hop(state)
            await self._run_reflection(state)
            if state.verdict == "sufficient":
                break
        await self._run_synthesis(state)
        return state

    async def answer(
        self,
        question: str,
        bvids: Optional[list[str]] = None,
        workspace_pages: Optional[list[dict[str, Any]]] = None,
        k: Optional[int] = None,
        max_hops: Optional[int] = None,
    ) -> AgenticAnswer:
        rewrite_result = await self.rewriter.rewrite(question)
        state = AgenticState(
            question=question,
            bvids=bvids or [],
            workspace_pages=workspace_pages,
            k=k or settings.agentic_rag_top_k,
            max_hops=max_hops or settings.agentic_rag_max_hops,
            candidate_queries=self._build_candidate_queries(question, rewrite_result),
        )

        try:
            if self.graph:
                result = AgenticState.from_dict(await self.graph.ainvoke(state.to_dict()))
                synthesis_method = "langgraph_agentic"
            else:
                result = await self._fallback_loop(state)
                synthesis_method = "fallback_agentic"

            avg_recall = round(sum(result.recall_scores) / len(result.recall_scores), 3) if result.recall_scores else 0.0
            return AgenticAnswer(
                answer=result.answer or "没有生成有效答案。",
                sources=result.all_sources[:5],
                reasoning_steps=result.reasoning_steps,
                synthesis_method=synthesis_method,
                hops_used=result.hop,
                avg_recall_score=avg_recall,
            )
        except Exception as exc:
            logger.error(f"Agentic RAG failed: {exc}")
            raise


def create_agentic_rag_service(
    rag_service: Optional[RAGService] = None,
    rewriter: Optional[QueryRewriter] = None,
) -> AgenticRAGService:
    """创建一个新的 AgenticRAGService 实例（不缓存）。"""
    return AgenticRAGService(
        rag_service=rag_service or RAGService(),
        rewriter=rewriter,
    )


_agentic_rag_service: Optional[AgenticRAGService] = None


def get_agentic_rag_service(
    rag_service: Optional[RAGService] = None,
    rewriter: Optional[QueryRewriter] = None,
) -> AgenticRAGService:
    """获取 AgenticRAGService 实例。

    如果传入任何参数，总是创建新实例（不缓存）。
    如果无参数且单例已存在，返回单例；否则创建默认实例并缓存。
    """
    if rag_service is not None or rewriter is not None:
        return create_agentic_rag_service(rag_service, rewriter)

    global _agentic_rag_service
    if _agentic_rag_service is None:
        _agentic_rag_service = create_agentic_rag_service()
    return _agentic_rag_service
