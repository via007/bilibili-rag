"""
Bilibili RAG 知识库系统
对话路由 - 智能问答
"""
import asyncio
import json
import re
from collections import defaultdict
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

from app.database import get_db
from app.models import (
    AgenticChatResponse,
    ChatRequest,
    ChatResponse,
    FavoriteFolder,
    FavoriteVideo,
    VideoCache,
    WorkspacePage,
)
from app.config import settings
from app.routers.knowledge import get_rag_service
from app.services.query import RewriteResult, RewriteType, CONFIDENCE_THRESHOLD
from app.services.rag import get_agentic_rag_service
from app.services.rag.prompts import (
    qa_system_prompt,
    fallback_system_prompt,
    direct_system_prompt,
    db_list_system_prompt,
    db_summary_system_prompt,
    overview_system_prompt,
)

router = APIRouter(prefix="/chat", tags=["对话"])

def _get_llm() -> ChatOpenAI:
    """获取 LangChain LLM 实例（支持 LangSmith 自动追踪）"""
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="未配置 LLM API Key")
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        temperature=0.5,
    )

def _build_overview_messages(context: str, question: str) -> list:
    system = overview_system_prompt(context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _build_rag_messages(context: str, question: str) -> list:
    system = qa_system_prompt(context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _build_fallback_messages(context: str, question: str) -> list:
    system = fallback_system_prompt(context=context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _build_direct_messages(question: str) -> list:
    """通用回答（不查库）"""
    system = direct_system_prompt(question)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _build_direct_messages_with_context(context: str, question: str) -> list:
    """带收藏夹上下文的通用回答（引导用户提问）"""
    system = direct_system_prompt(question, title_context=context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _log_final_payload(route: str, messages: list, sources: list[dict]) -> None:
    """记录最终发送给 LLM 的内容与来源"""
    logger.info(f"最终路由: {route}")
    logger.info(f"最终消息: {messages}")
    logger.info(f"最终来源数量: {len(sources)}")

def _build_db_list_messages(context: str, question: str) -> list:
    """仅用标题/简介回答列表类问题"""
    system = db_list_system_prompt(context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _build_db_summary_messages(context: str, question: str) -> list:
    """仅用数据库内容回答总结类问题"""
    system = db_summary_system_prompt(context)
    return [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]

def _is_list_question(question: str) -> bool:
    """列表/清单类问题"""
    list_terms = ["有哪些", "有什么", "列表", "清单", "目录", "都有哪些", "列出", "罗列", "多少个", "几个"]
    return any(term in question for term in list_terms)

def _is_summary_question(question: str) -> bool:
    """总结/概括类问题"""
    summary_terms = ["总结", "概述", "概括", "分析", "梳理", "提炼", "回顾", "复盘", "要点", "重点", "关键点", "核心", "讲了什么", "讲些什么"]
    return any(term in question for term in summary_terms)

def _is_general_question(question: str) -> bool:
    """通用闲聊/与收藏无关的问题"""
    general_terms = ["你好", "嗨", "哈喽", "hello", "hi", "在吗", "你是谁", "你能做什么", "谢谢", "晚安", "早安", "早上好"]
    cleaned = re.sub(r"[\\W_]+", "", question, flags=re.UNICODE)
    lowered = cleaned.lower()
    residual = lowered
    for term in general_terms:
        residual = residual.replace(term.lower(), "")
    return residual == ""

def _is_collection_intent(question: str) -> bool:
    """是否显式指向收藏/视频/知识库"""
    terms = ["收藏", "收藏夹", "视频", "合集", "up主", "BV", "bv", "分P", "字幕", "知识库", "入库", "同步", "向量", "检索"]
    return any(term in question for term in terms)

def _is_overview_question(question: str) -> bool:
    """概览类问题（列表或总结）"""
    return _is_list_question(question) or _is_summary_question(question)

def _route_with_rules(question: str, is_collection_intent: bool, related: bool) -> str:
    """规则路由兜底"""
    if _is_general_question(question) and not is_collection_intent:
        return "direct"
    if _is_list_question(question):
        return "db_list"
    if _is_summary_question(question):
        return "db_content"
    if not related and not is_collection_intent:
        return "direct"
    return "vector"

async def _route_with_llm(question: str) -> tuple[Optional[str], str]:
    """使用 LLM 进行路由判断（LangChain 版本，支持 LangSmith 追踪）"""
    try:
        llm = _get_llm()
        system = (
            "你是一个查询路由专家。请根据用户问题，只输出以下四个标签之一：\n"
            "- direct：寒暄、闲聊、通用知识问答，或与用户收藏夹完全无关的问题\n"
            "- db_list：需要列出条目、清单、目录的问题（关键词：有哪些、有什么、列出、目录、清单）\n"
            "- db_content：需要对收藏夹整体内容进行总结、概览、分析的问题（关键词：总结、概述、概览、全库、整体）\n"
            "- vector：针对具体主题的深度问题，需要先从向量库检索相关内容再回答\n"
            "\n"
            "边界案例（务必注意）：\n"
            "Q: 你好 / 你是谁 / 谢谢 -> direct\n"
            "Q: 我收藏了哪些视频 / 有哪些关于哲学的视频 -> db_list\n"
            "Q: 总结我收藏夹里所有内容 / 概览一下我的收藏 -> db_content\n"
            "Q: 王德峰讲的中国哲学有什么核心观点 -> vector（需要先检索）\n"
            "Q: 中西方文化的差异是什么 -> vector（具体主题，需检索）\n"
            "Q: 除了王德峰，我还收藏了哪些哲学视频 -> db_list（列表类）\n"
            "\n"
            "只输出一个词（direct/db_list/db_content/vector），不要解释，不要加标点。"
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=question),
        ]
        resp = await llm.ainvoke(messages, temperature=0)
        text = (resp.content or "").strip()
        match = re.search(r"(direct|db_list|db_content|vector)", text)
        return (match.group(1) if match else None), text
    except Exception as e:
        logger.warning(f"LLM 路由失败: {e}")
        return None, ""

def _extract_keywords(question: str) -> List[str]:
    """提取用于过滤的关键词"""
    stopwords = {
        "什么", "怎么", "如何", "是否", "可以", "哪个", "哪些", "请问", "一下", "为什么",
        "有没有", "能不能", "能否", "是不是", "是什么", "多少", "哪里", "讲讲", "介绍",
        "总结", "概括", "分析", "解释", "说明", "评价", "区别", "内容", "视频",
    }
    keywords: List[str] = []
    for kw in re.findall(r"[\u4e00-\u9fff]{2,}", question):
        if kw not in stopwords and kw not in keywords:
            keywords.append(kw)
    for kw in re.findall(r"[A-Za-z0-9]{2,}", question):
        if kw not in keywords:
            keywords.append(kw)
    return keywords

def _filter_docs_by_keywords(docs: List[Document], question: str) -> List[Document]:
    """根据关键词过滤召回内容，减少噪声"""
    keywords = _extract_keywords(question)
    if not keywords:
        return []
    filtered: List[Document] = []
    for doc in docs:
        meta = doc.metadata or {}
        title = meta.get("title", "") or ""
        content = doc.page_content or ""
        if any(kw in title for kw in keywords) or any(kw in content for kw in keywords):
            filtered.append(doc)
    return filtered


def _merge_and_deduplicate(*doc_lists, per_video_k: int = 2) -> List[Document]:
    """
    合并多路检索结果，按相关性分数降序。

    策略：分组 Top-K（而非全局 bvid 去重）
    - 按 bvid 分组
    - 每组内按 score 降序取 top-K
    - 所有组合并后全局按 score 降序

    为什么不用全局去重？
    - 一个视频 = 多语义片段（chunk）
    - 全局去重会丢失同视频的其他相关片段
    - 分组 Top-K 保证每个视频最多 per_video_k 个片段
    """
    # 按 bvid 分组（Document 对象使用 .metadata.get()）
    grouped = defaultdict(list)
    for i, docs in enumerate(doc_lists):
        for j, doc in enumerate(docs):
            try:
                bvid = doc.metadata.get("bvid") if hasattr(doc, "metadata") else doc.get("bvid")
            except Exception as e:
                logger.warning(f"[MERGE_DEBUG] doc[{i}][{j}] metadata.get 异常: type(doc)={type(doc)}, err={e}")
                continue
            try:
                if not isinstance(bvid, str):
                    logger.warning(f"[MERGE_DEBUG] doc[{i}][{j}] bvid 类型异常: type={type(bvid)}, value={repr(bvid)[:100]}")
                    continue
                if bvid:
                    grouped[bvid].append(doc)
            except TypeError as te:
                logger.warning(f"[MERGE_DEBUG] grouped[bvid] 异常: bvid={repr(bvid)[:50]}, err={te}")
                raise

    # 每组内按 score 降序取 top-K
    final_docs = []
    for bvid, group in grouped.items():
        group_sorted = sorted(group, key=lambda x: x.metadata.get("score", 0) if hasattr(x, "metadata") else x.get("score", 0), reverse=True)
        final_docs.extend(group_sorted[:per_video_k])

    # 全局按 score 降序
    final_docs.sort(key=lambda x: x.metadata.get("score", 0) if hasattr(x, "metadata") else x.get("score", 0), reverse=True)
    return final_docs


async def _vector_search_with_rewrites(
    question: str,
    rewrite_result: RewriteResult,
    bvids: Optional[List[str]],
    k: int = 5,
    workspace_pages: Optional[List[dict]] = None,
) -> tuple[str, List[dict]]:
    """
    根据改写结果选择检索 query。
    策略优先级：step_back > sub_queries。
    只有命中策略且置信度 >= CONFIDENCE_THRESHOLD 时才使用改写检索。

    Args:
        question: 原始问题
        rewrite_result: 查询改写结果
        bvids: 视频 BV 列表
        k: 召回数量
        workspace_pages: 工作区选中的分P列表，用于精确过滤
    """
    rag = get_rag_service()
    rewrites = rewrite_result.rewrites

    # 诊断日志：检查 workspace_pages 中是否有异常的 list 类型值
    if workspace_pages:
        for wp in workspace_pages:
            for k_field, v in wp.items():
                if isinstance(v, list):
                    logger.warning(f"[WORKSPACE_DEBUG] workspace_pages 中发现 list 类型: {k_field}={v}")

    if not rewrites:
        # 无改写结果，降级为直接检索
        docs = rag.search(question, k=k, bvids=bvids if bvids else None, workspace_pages=workspace_pages)
        return _build_context_from_docs(docs)

    rewrite = rewrites[0]  # 只有第一个（最高置信度）策略会被使用

    # === 策略1：后退提示词 → 泛化 + 具体 双路并发检索 ===
    if rewrite.type == RewriteType.STEP_BACK and rewrite.confidence >= CONFIDENCE_THRESHOLD:
        # 类型安全访问（dataclass 属性）
        step_back_query = rewrite.metadata.step_back_query
        specific_query = rewrite.metadata.specific_query

        logger.info(
            f"[QUERY_REWRITE] step_back confidence={rewrite.confidence}\n"
            f"  原始问题: {question}\n"
            f"  泛化 query: {step_back_query}\n"
            f"  具体 query: {specific_query}\n"
            f"  并发检索双路..."
        )

        # 并发执行，不在关键路径上增加延迟
        general_docs, specific_docs = await asyncio.gather(
            rag.search(step_back_query, k=k, bvids=bvids if bvids else None, workspace_pages=workspace_pages),
            rag.search(specific_query, k=k, bvids=bvids if bvids else None, workspace_pages=workspace_pages),
        )
        logger.info(
            f"[QUERY_REWRITE] 泛化召回: {len(general_docs)} docs, "
            f"具体召回: {len(specific_docs)} docs"
        )
        docs = _merge_and_deduplicate(general_docs, specific_docs)
        logger.info(f"[QUERY_REWRITE] 合并后总召回: {len(docs)} docs")
        return _build_context_from_docs(docs)

    # === 策略2：子查询拆分 → 所有子 query 并发检索 ===
    if rewrite.type == RewriteType.SUB_QUERIES and rewrite.confidence >= CONFIDENCE_THRESHOLD:
        # 类型安全访问（dataclass 属性）
        sub_queries = rewrite.metadata.sub_queries

        logger.info(
            f"[QUERY_REWRITE] sub_queries confidence={rewrite.confidence}\n"
            f"  原始问题: {question}\n"
            f"  拆分数量: {len(sub_queries)} 路\n"
            f"  子查询列表: {sub_queries}\n"
            f"  并发检索..."
        )

        # 并发执行所有子 query 检索
        results = await asyncio.gather(*[
            rag.search(q, k=k, bvids=bvids if bvids else None, workspace_pages=workspace_pages) for q in sub_queries
        ])
        for i, (q, r) in enumerate(zip(sub_queries, results)):
            logger.info(f"[QUERY_REWRITE] 子查询[{i+1}] '{q}' 召回: {len(r)} docs")
        docs = _merge_and_deduplicate(*results)
        logger.info(f"[QUERY_REWRITE] 合并后总召回: {len(docs)} docs")
        return _build_context_from_docs(docs)

    # === 兜底：直接检索 ===
    logger.warning(
        f"[QUERY_REWRITE] 未命中任何改写策略，使用原始 question 直接检索\n"
        f"  rewrite.type={rewrite.type}, confidence={rewrite.confidence}"
    )
    docs = rag.search(question, k=k, bvids=bvids if bvids else None, workspace_pages=workspace_pages)
    return _build_context_from_docs(docs)


def _build_context_from_docs(docs: List[Document]) -> tuple[str, List[dict]]:
    """从文档列表构建 context 和 sources"""
    context_parts, sources, seen_bvids = [], [], set()
    for doc in docs:
        try:
            bvid = doc.metadata.get("bvid", "") if hasattr(doc, "metadata") else (doc.get("bvid", "") if hasattr(doc, "get") else "")
            title = doc.metadata.get("title", "") if hasattr(doc, "metadata") else (doc.get("title", "") if hasattr(doc, "get") else "")
            content = doc.page_content.strip() if hasattr(doc, "page_content") else str(doc).strip()
        except Exception as e:
            logger.warning(f"[BUILD_CTX_DEBUG] doc 处理异常: type(doc)={type(doc)}, err={e}")
            continue
        if content:
            context_parts.append(f"【{title}】\n{content}")
        # 防御：bvid 可能是 list 或其他非 hashable 类型
        if bvid and isinstance(bvid, str) and bvid not in seen_bvids:
            seen_bvids.add(bvid)
            sources.append({"bvid": bvid, "title": title, "url": f"https://www.bilibili.com/video/{bvid}"})
    return "\n\n---\n\n".join(context_parts), sources

async def _is_related_to_collection(db: AsyncSession, folder_ids: List[int], question: str) -> bool:
    """判断问题是否与收藏夹内容有关"""
    if not folder_ids:
        return False
    keywords = _extract_keywords(question)
    if not keywords:
        return False
    like_conds = []
    for kw in keywords:
        pattern = f"%{kw}%"
        like_conds.append(VideoCache.title.ilike(pattern))
        like_conds.append(VideoCache.description.ilike(pattern))
        like_conds.append(VideoCache.content.ilike(pattern))
    stmt = (
        select(func.count())
        .select_from(VideoCache)
        .join(FavoriteVideo, FavoriteVideo.bvid == VideoCache.bvid)
        .where(FavoriteVideo.folder_id.in_(folder_ids))
        .where(or_(*like_conds))
    )
    count = await db.scalar(stmt)
    return (count or 0) > 0

async def _get_folder_ids_for_session(db: AsyncSession, session_id: str, media_ids: Optional[List[int]]) -> List[int]:
    """根据 session 和 media_id 获取内部 folder_id（支持跨 session 查找同用户数据）"""
    from app.models import UserSession
    # 1. 尝试获取当前 session 的 mid
    mid_result = await db.execute(select(UserSession.bili_mid).where(UserSession.session_id == session_id))
    mid = mid_result.scalar()
    target_session_ids = [session_id]
    if mid:
        # 查找该用户所有的 Session ID
        sessions_result = await db.execute(select(UserSession.session_id).where(UserSession.bili_mid == mid))
        target_session_ids = [row[0] for row in sessions_result.fetchall()]
    # 构建查询：按 media_id 去重，只保留最新的一条
    stmt = (
        select(FavoriteFolder.id, FavoriteFolder.media_id, FavoriteFolder.updated_at)
        .where(FavoriteFolder.session_id.in_(target_session_ids))
        .order_by(FavoriteFolder.updated_at.desc())
    )
    if media_ids:
        stmt = stmt.where(FavoriteFolder.media_id.in_(media_ids))
    rows = await db.execute(stmt)
    dedup: dict[int, int] = {}
    for folder_id, media_id, _updated_at in rows.fetchall():
        if media_id not in dedup:
            dedup[media_id] = folder_id
    return list(dedup.values())

async def _get_bvids_by_folder_ids(db: AsyncSession, folder_ids: List[int]) -> List[str]:
    """获取指定收藏夹的视频 BV 列表"""
    if not folder_ids:
        return []
    rows = await db.execute(select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id.in_(folder_ids)))
    bvids = []
    seen = set()
    for (bvid,) in rows.fetchall():
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        bvids.append(bvid)
    return bvids

async def _get_video_context(db: AsyncSession, folder_ids: List[int], include_content: bool = False, limit: Optional[int] = 50) -> tuple[str, List[dict]]:
    """获取视频上下文信息"""
    if not folder_ids:
        return "", []
    # 查询视频信息
    query = (
        select(
            FavoriteFolder.title.label("folder_title"),
            VideoCache.bvid,
            VideoCache.title,
            VideoCache.description,
            VideoCache.content if include_content else VideoCache.description,
        )
        .join(FavoriteVideo, FavoriteVideo.folder_id == FavoriteFolder.id)
        .join(VideoCache, VideoCache.bvid == FavoriteVideo.bvid, isouter=True)
        .where(FavoriteFolder.id.in_(folder_ids))
    )
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    records = result.fetchall()
    if not records:
        return "", []
    # 按收藏夹分组（对 bvid 去重，避免同一视频重复出现）
    grouped = {}
    sources = []
    seen_bvids = set()
    for folder_title, bvid, title, desc, content in records:
        if not bvid or not title:
            continue
        if bvid in seen_bvids:
            continue
        folder_name = folder_title or "默认收藏夹"
        if folder_name not in grouped:
            grouped[folder_name] = []
        video_info = f"- 《{title}》"
        if include_content and content:
            video_info += f"\n  摘要: {content}"
        elif desc:
            short_desc = desc[:100] + "..." if len(desc) > 100 else desc
            video_info += f" ({short_desc})"
        grouped[folder_name].append(video_info)
        seen_bvids.add(bvid)
        sources.append({"bvid": bvid, "title": title, "url": f"https://www.bilibili.com/video/{bvid}"})
    # 构建上下文文本
    context_parts = [f"【{folder_name}】\n" + "\n".join(videos) for folder_name, videos in grouped.items()]
    context = "\n\n".join(context_parts)
    return context, sources

async def _get_video_titles_context(db: AsyncSession, folder_ids: List[int], limit: int = 50) -> str:
    """获取收藏夹名称与视频标题（用于引导问题）"""
    if not folder_ids:
        return ""
    query = (
        select(FavoriteFolder.title.label("folder_title"), VideoCache.bvid, VideoCache.title)
        .join(FavoriteVideo, FavoriteVideo.folder_id == FavoriteFolder.id)
        .join(VideoCache, VideoCache.bvid == FavoriteVideo.bvid, isouter=True)
        .where(FavoriteFolder.id.in_(folder_ids))
        .limit(limit)
    )
    result = await db.execute(query)
    records = result.fetchall()
    if not records:
        return ""
    grouped = {}
    seen_bvids = set()
    for folder_title, bvid, title in records:
        if not title or not bvid:
            continue
        if bvid in seen_bvids:
            continue
        seen_bvids.add(bvid)
        folder_name = folder_title or "默认收藏夹"
        grouped.setdefault(folder_name, []).append(f"- 《{title}》")
    context_parts = [f"【{folder_name}】\n" + "\n".join(videos) for folder_name, videos in grouped.items()]
    return "\n\n".join(context_parts)

async def _prepare_messages(request: ChatRequest, db: AsyncSession, rewrite_result: Optional[RewriteResult] = None) -> tuple[list, List[dict], str, Optional[RewriteResult]]:
    """准备 LLM 消息与来源信息"""
    question = request.question.strip()
    rag = get_rag_service()
    folder_ids = []
    if request.session_id:
        folder_ids = await _get_folder_ids_for_session(db, request.session_id, request.folder_ids)
        logger.info(f"Session: {request.session_id}, 关联 FolderIDs: {folder_ids}")
    bvids = await _get_bvids_by_folder_ids(db, folder_ids) if folder_ids else []
    has_data = len(bvids) > 0
    is_collection_intent = _is_collection_intent(question)
    is_general = _is_general_question(question)
    if request.folder_ids:
        is_collection_intent = True

    # 工作区模式：有 workspace_pages 时强制走 vector 检索
    workspace_mode = request.workspace_pages is not None and len(request.workspace_pages) > 0
    workspace_pages_dicts = [wp.model_dump() for wp in request.workspace_pages] if workspace_mode else None
    if workspace_mode:
        logger.info(f"[WORKSPACE] 工作区模式: {len(workspace_pages_dicts)} 个分P")

    # 1) LLM 路由优先，失败时降级规则路由
    logger.info(f"路由输入: question={question} folder_ids={folder_ids} has_data={has_data} is_collection_intent={is_collection_intent}")
    route, route_raw = await _route_with_llm(question)
    route_source = "LLM"
    related: Optional[bool] = None
    if not route:
        related = await _is_related_to_collection(db, folder_ids, question)
        route = _route_with_rules(question, is_collection_intent, related)
        route_source = "RULE"
    logger.info(f"路由策略: {route_source} => {route}")
    # 纠偏
    if is_general:
        route = "direct"
    # 工作区模式强制走 vector
    if workspace_mode:
        route = "vector"
        logger.info("[WORKSPACE] 强制路由: vector")
    # 2) 无数据时处理
    if not has_data:
        if is_collection_intent:
            context, sources = await _get_video_context(db, folder_ids, include_content=False, limit=50)
            if not context:
                context = "（暂无已入库的视频信息，请提醒用户可能需要先进行入库操作）"
            messages = _build_fallback_messages(context, question)
            return messages, sources, question, rewrite_result
        messages = _build_direct_messages(question)
        return messages, [], question, rewrite_result
    # 3) 直接回答
    if route == "direct":
        title_context = await _get_video_titles_context(db, folder_ids, limit=50)
        messages = _build_direct_messages_with_context(title_context, question) if title_context else _build_direct_messages(question)
        return messages, [], question, rewrite_result
    # 4) 列表类问题
    if route == "db_list":
        if related is None:
            related = await _is_related_to_collection(db, folder_ids, question)
        if not related and not is_collection_intent:
            return _build_direct_messages(question), [], question, rewrite_result
        context, sources = await _get_video_context(db, folder_ids, include_content=False, limit=50)
        if not context:
            return _build_fallback_messages("（暂无信息，请入库）", question), sources, question, rewrite_result
        return _build_db_list_messages(context, question), sources, question, rewrite_result
    # 5) 总结类问题
    if route == "db_content":
        if related is None:
            related = await _is_related_to_collection(db, folder_ids, question)
        if not related and not is_collection_intent:
            return _build_direct_messages(question), [], question, rewrite_result
        context, sources = await _get_video_context(db, folder_ids, include_content=True, limit=None)
        if not context:
            return _build_fallback_messages("（暂无信息，请入库）", question), sources, question, rewrite_result
        return _build_db_summary_messages(context, question), sources, question, rewrite_result
    # 6) 检查相关性（使用改写后的 query 以提升语义匹配）
    if related is None:
        rewrite_query = rewrite_result.rewrites[0].query if (rewrite_result and rewrite_result.rewrites) else question
        related = await _is_related_to_collection(db, folder_ids, rewrite_query)
    if not related and not is_collection_intent and not workspace_mode:
        return _build_direct_messages(question), [], question, rewrite_result
    # 7) 向量检索（使用 Query 改写 + 工作区过滤）
    try:
        context, sources = await _vector_search_with_rewrites(
            question, rewrite_result, bvids, k=5, workspace_pages=workspace_pages_dicts
        )
        if context:
            return _build_rag_messages(context, question), sources, question, rewrite_result
    except Exception as e:
        logger.warning(f"向量检索失败: {e}")
    # 兜底
    context, sources = await _get_video_context(db, folder_ids, include_content=False, limit=50)
    return _build_fallback_messages(context or "（暂无入库信息）", question), sources, question, rewrite_result

@router.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    """智能问答"""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    try:
        # === Query 改写 ===
        rewriter = http_request.app.state.rewriter
        rewrite_result = await rewriter.rewrite(request.question.strip())
        logger.info(f"[QUERY_REWRITE] original={request.question.strip()}")
        logger.info(f"[QUERY_REWRITE] rewrites={[(r.type.value, r.query[:50], r.confidence) for r in rewrite_result.rewrites]}")
        logger.info(f"[QUERY_REWRITE] suggested_route={rewrite_result.suggested_route}, needs_rewrite={rewrite_result.needs_rewrite}")

        messages, sources, _, _ = await _prepare_messages(request, db, rewrite_result)
        llm = _get_llm()
        response = await llm.ainvoke(messages)
        return ChatResponse(answer=response.content or "", sources=sources[:5])
    except HTTPException: raise
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


@router.post("/ask/agentic", response_model=AgenticChatResponse)
async def ask_question_agentic(request: ChatRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    """Agentic RAG 问答"""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        folder_ids = []
        if request.session_id:
            folder_ids = await _get_folder_ids_for_session(db, request.session_id, request.folder_ids)
        bvids = await _get_bvids_by_folder_ids(db, folder_ids) if folder_ids else []
        workspace_pages = [wp.model_dump() for wp in request.workspace_pages] if request.workspace_pages else None

        service = get_agentic_rag_service(
            rag_service=get_rag_service(),
            rewriter=http_request.app.state.rewriter,
        )
        result = await service.answer(
            question=request.question.strip(),
            bvids=bvids,
            workspace_pages=workspace_pages,
        )
        return AgenticChatResponse(
            answer=result.answer,
            sources=result.sources,
            reasoning_steps=[step.model_dump() for step in result.reasoning_steps],
            synthesis_method=result.synthesis_method,
            hops_used=result.hops_used,
            avg_recall_score=result.avg_recall_score,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agentic RAG 问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"Agentic RAG 问答失败: {str(e)}")

@router.post("/ask/stream")
async def ask_question_stream(request: ChatRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    """流式问答"""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    try:
        # === Query 改写 ===
        rewriter = http_request.app.state.rewriter
        rewrite_result = await rewriter.rewrite(request.question.strip())
        logger.info(f"[QUERY_REWRITE] original={request.question.strip()}")
        logger.info(f"[QUERY_REWRITE] rewrites={[(r.type.value, r.query[:50], r.confidence) for r in rewrite_result.rewrites]}")
        logger.info(f"[QUERY_REWRITE] suggested_route={rewrite_result.suggested_route}, needs_rewrite={rewrite_result.needs_rewrite}")

        messages, sources, _, _ = await _prepare_messages(request, db, rewrite_result)
        llm = _get_llm()

        # 获取 rewrite 信息用于附加到 sources
        rewrite = rewrite_result.rewrites[0] if rewrite_result.rewrites else None
        rewrite_info = None
        if rewrite:
            rewrite_info = {
                "used_rewrite": rewrite.type.value,
                "rewrite_query": rewrite.query[:50] if rewrite.query else None,
                "confidence": rewrite.confidence,
            }

        async def generate():
            """标准 SSE 流式生成器（data: 前缀 + event type）"""
            try:
                async for chunk in llm.astream(messages):
                    data = json.dumps({"type": "chunk", "content": chunk.content or ""}, ensure_ascii=False)
                    yield f"data: {data}\n\n"

                # 附加 sources 和 rewrite 信息
                sources_payload = json.dumps({
                    "type": "sources",
                    "sources": sources,
                    "rewrite_info": rewrite_info,
                }, ensure_ascii=False)
                yield f"data: {sources_payload}\n\n"

                # 结束标记
                done_payload = json.dumps({"type": "done"}, ensure_ascii=False)
                yield f"data: {done_payload}\n\n"
            except Exception as e:
                logger.error(f"流式生成失败: {e}")
                error_payload = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    except HTTPException: raise
    except Exception as e:
        logger.error(f"流式问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"流式问答失败: {str(e)}")

@router.post("/search")
async def search_videos(query: str, k: int = 5):
    """搜索相关视频片段"""
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="查询不能为空")
    try:
        rag = get_rag_service()
        docs = rag.search(query, k=k)
        results, seen_bvids = [], set()
        for doc in docs:
            bvid = doc.metadata.get("bvid", "")
            if bvid in seen_bvids: continue
            seen_bvids.add(bvid)
            results.append({
                "bvid": bvid,
                "title": doc.metadata.get("title", ""),
                "url": doc.metadata.get("url", ""),
                "content_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            })
        return {"results": results}
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")
