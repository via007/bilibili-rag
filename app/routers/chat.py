"""
Bilibili RAG 知识库系统

对话路由 - 智能问答
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from typing import List, Optional
import re
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from openai import OpenAI
from langchain.schema import Document

from app.database import get_db
from app.models import ChatRequest, ChatResponse, FavoriteFolder, FavoriteVideo, VideoCache
from app.config import settings
from app.routers.knowledge import get_rag_service

router = APIRouter(prefix="/chat", tags=["对话"])


def _get_llm_client() -> OpenAI:
    """获取 LLM 客户端"""
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="未配置 LLM API Key")
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def _build_overview_messages(context: str, question: str) -> list[dict]:
    system = (
        "你是一个收藏夹知识库助手。用户想要了解他们收藏夹的整体内容。\n"
        "请根据以下视频信息回答用户的问题。回答要：\n"
        "1. 自然、友好、有条理\n"
        "2. 可以总结、分类、提炼要点\n"
        "3. 如果内容较多，挑选代表性的进行介绍\n\n"
        f"收藏夹内容：\n{context}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _build_rag_messages(context: str, question: str) -> list[dict]:
    system = (
        "你是一个知识库助手，基于用户收藏的视频内容回答问题。\n"
        "请根据以下检索到的视频内容回答：\n"
        "1. 直接回答问题，引用相关内容\n"
        "2. 回答要自然、有条理\n"
        "3. 可以引用视频标题作为来源\n\n"
        f"相关内容：\n{context}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _build_fallback_messages(context: str, question: str) -> list[dict]:
    system = (
        "你是一个收藏夹知识库助手。\n"
        "用户的问题在现有知识库中没有检索到直接内容。\n"
        "以下是用户收藏夹中的视频概览（如果为空说明用户还没入库）：\n"
        f"{context}\n\n"
        "请根据以上信息（如果有）：\n"
        "1. 尝试回答用户问题\n"
        "2. 如果没有任何视频信息，礼貌地告诉用户需要先在左侧选择收藏夹并点击「入库」或者「更新」\n"
        "3. 保持像真人助手一样的语气，不要显示这是\"备选方案\""
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _build_direct_messages(question: str) -> list[dict]:
    """通用回答（不查库）"""
    system = (
        "你是一个友好、简洁的助手。\n"
        "请直接回答用户问题，避免引入收藏夹或知识库内容。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _build_direct_messages_with_context(context: str, question: str) -> list[dict]:
    """带收藏夹上下文的通用回答（引导用户提问）"""
    system = (
        "你是一个友好、简洁的助手。\n"
        "以下是用户收藏夹的概览（收藏夹名称与视频标题）：\n"
        f"{context}\n\n"
        "请先回答用户问题，再根据收藏夹内容引导用户提出与收藏相关的问题。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _log_final_payload(route: str, messages: list[dict], sources: list[dict]) -> None:
    """记录最终发送给 LLM 的内容与来源"""
    logger.info(f"最终路由: {route}")
    logger.info(f"最终消息: {messages}")
    logger.info(f"最终来源数量: {len(sources)}")

def _build_db_list_messages(context: str, question: str) -> list[dict]:
    """仅用标题/简介回答列表类问题"""
    system = (
        "你是一个收藏夹知识库助手。\n"
        "用户需要清单/列表类答案，请基于以下视频标题与简介回答。\n"
        "回答要：\n"
        "1. 按收藏夹或主题分组\n"
        "2. 只输出与问题相关的条目\n"
        "3. 简洁清晰\n\n"
        f"收藏夹内容：\n{context}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _build_db_summary_messages(context: str, question: str) -> list[dict]:
    """仅用数据库内容回答总结类问题"""
    system = (
        "你是一个收藏夹知识库助手。\n"
        "用户需要总结/提炼，请基于以下视频内容回答。\n"
        "回答要：\n"
        "1. 提炼重点与要点\n"
        "2. 结构清晰、可快速理解\n"
        "3. 必要时引用视频标题作为来源\n\n"
        f"收藏夹内容：\n{context}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def _is_list_question(question: str) -> bool:
    """列表/清单类问题"""
    list_terms = [
        "有哪些", "有什么", "列表", "清单", "目录", "都有哪些",
        "列出", "罗列", "多少个", "几个"
    ]
    return any(term in question for term in list_terms)


def _is_summary_question(question: str) -> bool:
    """总结/概括类问题"""
    summary_terms = [
        "总结", "概述", "概括", "分析", "梳理", "提炼", "回顾",
        "复盘", "要点", "重点", "关键点", "核心", "讲了什么", "讲些什么"
    ]
    return any(term in question for term in summary_terms)


def _is_general_question(question: str) -> bool:
    """通用闲聊/与收藏无关的问题"""
    general_terms = [
        "你好", "嗨", "哈喽", "hello", "hi", "在吗",
        "你是谁", "你能做什么", "谢谢", "晚安", "早安", "早上好"
    ]
    return any(term.lower() in question.lower() for term in general_terms)


def _is_collection_intent(question: str) -> bool:
    """是否显式指向收藏/视频/知识库"""
    terms = [
        "收藏", "收藏夹", "视频", "合集", "up主", "BV", "bv",
        "分P", "字幕", "知识库", "入库", "同步", "向量", "检索"
    ]
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


def _route_with_llm(question: str) -> tuple[Optional[str], str]:
    """使用 LLM 进行路由判断"""
    try:
        client = _get_llm_client()
        system = (
            "你是一个路由器，只输出以下之一：direct, db_list, db_content, vector。\n"
            "含义：\n"
            "- direct：通用问题，直接回答，不查库\n"
            "- db_list：清单/列表/有哪些类问题，用标题/简介\n"
            "- db_content：总结/概括/复盘类问题，用内容\n"
            "- vector：具体语义问题，需要向量检索\n"
            "只输出一个词，不要解释。"
        )
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
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


async def _is_related_to_collection(
    db: AsyncSession, folder_ids: List[int], question: str
) -> bool:
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


async def _get_folder_ids_for_session(
    db: AsyncSession, session_id: str, media_ids: Optional[List[int]]
) -> List[int]:
    """根据 session 和 media_id 获取内部 folder_id（支持跨 session 查找同用户数据）"""
    from app.models import UserSession
    
    # 1. 尝试获取当前 session 的 mid
    mid_result = await db.execute(
        select(UserSession.bili_mid).where(UserSession.session_id == session_id)
    )
    mid = mid_result.scalar()
    
    target_session_ids = [session_id]
    
    if mid:
        # 查找该用户所有的 Session ID
        sessions_result = await db.execute(
            select(UserSession.session_id).where(UserSession.bili_mid == mid)
        )
        target_session_ids = [row[0] for row in sessions_result.fetchall()]
    
    # 构建查询
    stmt = select(FavoriteFolder.id).where(FavoriteFolder.session_id.in_(target_session_ids))
    
    if media_ids:
        stmt = stmt.where(FavoriteFolder.media_id.in_(media_ids))
        
    rows = await db.execute(stmt)
    return [row[0] for row in rows.fetchall()]


async def _get_bvids_by_folder_ids(db: AsyncSession, folder_ids: List[int]) -> List[str]:
    """获取指定收藏夹的视频 BV 列表"""
    if not folder_ids:
        return []
    rows = await db.execute(
        select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id.in_(folder_ids))
    )
    return [row[0] for row in rows.fetchall()]


async def _get_video_context(
    db: AsyncSession, folder_ids: List[int], include_content: bool = False, limit: int = 50
) -> tuple[str, List[dict]]:
    """
    获取视频上下文信息
    """
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
        .limit(limit)
    )
    
    result = await db.execute(query)
    records = result.fetchall()
    
    if not records:
        return "", []
    
    # 按收藏夹分组
    grouped = {}
    sources = []
    seen_bvids = set()
    
    for folder_title, bvid, title, desc, content in records:
        if not bvid or not title:
            continue
        
        folder_name = folder_title or "默认收藏夹"
        if folder_name not in grouped:
            grouped[folder_name] = []
        
        video_info = f"- 《{title}》"
        if include_content and content:
            # 截取摘要
            summary = content[:500] + "..." if len(content) > 500 else content
            video_info += f"\n  摘要: {summary}"
        elif desc:
            short_desc = desc[:100] + "..." if len(desc) > 100 else desc
            video_info += f" ({short_desc})"
        
        grouped[folder_name].append(video_info)
        
        if bvid not in seen_bvids:
            seen_bvids.add(bvid)
            sources.append({
                "bvid": bvid,
                "title": title,
                "url": f"https://www.bilibili.com/video/{bvid}"
            })
    
    # 构建上下文文本
    context_parts = []
    for folder_name, videos in grouped.items():
        context_parts.append(f"【{folder_name}】\n" + "\n".join(videos))
    
    context = "\n\n".join(context_parts)
    return context, sources


async def _get_video_titles_context(
    db: AsyncSession, folder_ids: List[int], limit: int = 50
) -> str:
    """获取收藏夹名称与视频标题（用于引导问题）"""
    if not folder_ids:
        return ""

    query = (
        select(
            FavoriteFolder.title.label("folder_title"),
            VideoCache.title,
        )
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
    for folder_title, title in records:
        if not title:
            continue
        folder_name = folder_title or "默认收藏夹"
        grouped.setdefault(folder_name, []).append(f"- 《{title}》")

    context_parts = []
    for folder_name, videos in grouped.items():
        context_parts.append(f"【{folder_name}】\n" + "\n".join(videos))

    return "\n\n".join(context_parts)


async def _prepare_messages(
    request: ChatRequest,
    db: AsyncSession,
) -> tuple[list[dict], List[dict], str]:
    """准备 LLM 消息与来源信息"""
    question = request.question.strip()
    rag = get_rag_service()

    folder_ids = []
    if request.session_id:
        folder_ids = await _get_folder_ids_for_session(
            db, request.session_id, request.folder_ids
        )
        logger.info(f"Session: {request.session_id}, 关联 FolderIDs: {folder_ids}")

    bvids = await _get_bvids_by_folder_ids(db, folder_ids) if folder_ids else []
    has_data = len(bvids) > 0

    is_collection_intent = _is_collection_intent(question)

    # 1) LLM 路由优先，失败时降级规则路由
    logger.info(
        f"路由输入: question={question} folder_ids={folder_ids} has_data={has_data} "
        f"is_collection_intent={is_collection_intent}"
    )
    route, route_raw = _route_with_llm(question)
    route_source = "LLM"
    related: Optional[bool] = None
    if route:
        logger.info(f"路由输出: raw={route_raw} parsed={route}")
    else:
        related = await _is_related_to_collection(db, folder_ids, question)
        route = _route_with_rules(question, is_collection_intent, related)
        route_source = "RULE"
        logger.info(f"路由输出: raw={route_raw} parsed={route}")
    logger.info(f"路由策略: {route_source} => {route}")

    # 纠偏：LLM 误判 direct 时，优先使用规则路由（有收藏数据时）
    if route_source == "LLM" and route == "direct" and has_data:
        if related is None:
            related = await _is_related_to_collection(db, folder_ids, question)
        rule_route = _route_with_rules(question, is_collection_intent, related)
        if rule_route != "direct":
            logger.info(f"路由修正: direct -> {rule_route}")
            route = rule_route
    if has_data and route == "direct" and not _is_general_question(question):
        logger.info("路由修正: direct -> vector (优先检索)")
        route = "vector"

    # 2) 无数据时：收藏相关问题提示入库，非收藏问题直接回答
    if not has_data:
        if is_collection_intent:
            logger.info("路由策略: fallback_no_data")
            context, sources = await _get_video_context(
                db, folder_ids, include_content=False, limit=50
            )
            if not context:
                context = "（暂无已入库的视频信息，请提醒用户可能需要先进行入库操作）"
            messages = _build_fallback_messages(context, question)
            _log_final_payload("fallback_no_data", messages, sources)
            return messages, sources, question
        logger.info("路由策略: direct_no_data")
        messages = _build_direct_messages(question)
        _log_final_payload("direct_no_data", messages, [])
        return messages, [], question

    # 3) 直接回答
    if route == "direct":
        if has_data:
            title_context = await _get_video_titles_context(db, folder_ids, limit=50)
            if title_context:
                messages = _build_direct_messages_with_context(title_context, question)
            else:
                messages = _build_direct_messages(question)
        else:
            messages = _build_direct_messages(question)
        _log_final_payload("direct", messages, [])
        return messages, [], question

    # 4) 列表/概览类问题：查数据库标题/简介
    if route == "db_list":
        if related is None:
            related = await _is_related_to_collection(db, folder_ids, question)
        if not related and not is_collection_intent:
            logger.info("路由修正: db_list -> direct (无收藏关联)")
            messages = _build_direct_messages(question)
            _log_final_payload("direct", messages, [])
            return messages, [], question
        context, sources = await _get_video_context(
            db, folder_ids, include_content=False, limit=50
        )
        if not context:
            context = "（暂无已入库的视频信息，请提醒用户可能需要先进行入库操作）"
            messages = _build_fallback_messages(context, question)
            _log_final_payload("fallback_no_data", messages, sources)
            return messages, sources, question
        messages = _build_db_list_messages(context, question)
        _log_final_payload("db_list", messages, sources)
        return messages, sources, question

    # 5) 总结类问题：查数据库内容
    if route == "db_content":
        if related is None:
            related = await _is_related_to_collection(db, folder_ids, question)
        if not related and not is_collection_intent:
            logger.info("路由修正: db_content -> direct (无收藏关联)")
            messages = _build_direct_messages(question)
            _log_final_payload("direct", messages, [])
            return messages, [], question
        context, sources = await _get_video_context(
            db, folder_ids, include_content=True, limit=30
        )
        if not context:
            context = "（暂无已入库的视频信息，请提醒用户可能需要先进行入库操作）"
            messages = _build_fallback_messages(context, question)
            _log_final_payload("fallback_no_data", messages, sources)
            return messages, sources, question
        messages = _build_db_summary_messages(context, question)
        _log_final_payload("db_content", messages, sources)
        return messages, sources, question

    # 6) 判断是否与收藏相关（不相关则直接回答）
    if related is None:
        related = await _is_related_to_collection(db, folder_ids, question)
    if not related and not is_collection_intent:
        logger.info("路由策略: direct_unrelated")
        messages = _build_direct_messages(question)
        _log_final_payload("direct_unrelated", messages, [])
        return messages, [], question

    # 7) 具体问题：向量检索
    logger.info(f"具体问题: {question[:50]}...")
    logger.info(f"检索范围: {len(bvids)} 个 BV")

    docs = []
    try:
        docs = rag.search(question, k=5, bvids=bvids if bvids else None)
        logger.info(f"检索结果: {len(docs)} 条文档")
    except Exception as e:
        logger.warning(f"向量检索失败: {e}")

    if docs:
        filtered_docs = _filter_docs_by_keywords(docs, question)
        if filtered_docs:
            docs = filtered_docs
            logger.info(f"关键词过滤后: {len(docs)} 条文档")
        else:
            logger.info("关键词过滤后为空，使用原召回结果")

    if docs:
        context_parts = []
        sources = []
        seen_bvids = set()

        for doc in docs:
            bvid = doc.metadata.get("bvid", "")
            title = doc.metadata.get("title", "")
            content = doc.page_content.strip()

            if content:
                context_parts.append(f"【{title}】\n{content}")

            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                sources.append({
                    "bvid": bvid,
                    "title": title,
                    "url": f"https://www.bilibili.com/video/{bvid}"
                })

        context = "\n\n---\n\n".join(context_parts)
        messages = _build_rag_messages(context, question)
        _log_final_payload("vector", messages, sources)
        return messages, sources, question

    # 没检索到，用视频列表作为备选上下文
    logger.info("未检索到相关内容，使用标题列表...")
    context, sources = await _get_video_context(
        db, folder_ids, include_content=False, limit=50
    )

    if not context:
        context = "（暂无已入库的视频信息，请提醒用户可能需要先进行入库操作）"

    messages = _build_fallback_messages(context, question)
    _log_final_payload("fallback", messages, sources)
    return messages, sources, question


@router.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    智能问答
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        messages, sources, question = await _prepare_messages(request, db)
        client = _get_llm_client()

        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.5,
        )
        answer = response.choices[0].message.content or ""

        return ChatResponse(answer=answer, sources=sources[:5])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


@router.post("/ask/stream")
async def ask_question_stream(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """流式问答"""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        import json
        messages, sources, _ = await _prepare_messages(request, db)
        client = _get_llm_client()

        def generate():
            stream = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=0.5,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            marker = "[[SOURCES_JSON]]"
            yield f"\n{marker}{json.dumps(sources, ensure_ascii=False)}"

        return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")

    except HTTPException:
        raise
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
        
        results = []
        seen_bvids = set()
        
        for doc in docs:
            bvid = doc.metadata.get("bvid", "")
            if bvid in seen_bvids:
                continue
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
