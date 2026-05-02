"""
Bilibili RAG 知识库系统

RAG 服务模块 - 向量存储与问答
"""
from typing import List, Optional, TYPE_CHECKING
from loguru import logger
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain.schema import Document
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import settings
from app.models import VideoContent
from app.services.rag.chunking import SemanticChunker
from app.services.rag.prompts import (
    qa_system_prompt,
    fallback_system_prompt,
    summary_system_prompt,
)

if TYPE_CHECKING:
    from app.services.llm.api_key_manager import ApiKeyManager


class RAGService:
    """
    RAG 服务

    负责：
    1. 向量存储管理
    2. 文档添加与检索
    3. 问答功能

    支持用户自定义 API Key（通过 ApiKeyManager + DynamicEmbeddings）。
    """

    def __init__(
        self,
        collection_name: str = "bilibili_videos",
        api_key_manager: Optional["ApiKeyManager"] = None,
    ):
        """
        初始化 RAG 服务

        Args:
            collection_name: 向量集合名称
            api_key_manager: 用户 API Key 管理器（可选，支持动态 Embedding Key）
        """
        self.collection_name = collection_name
        self._api_key_manager = api_key_manager

        # 默认配置
        default_embedding_api_key = settings.openai_api_key
        default_embedding_base_url = settings.openai_base_url
        default_embedding_model = settings.embedding_model

        # 初始化 Embeddings
        if api_key_manager and api_key_manager.is_enabled:
            from app.services.llm.dynamic_embeddings import DynamicEmbeddings
            self.embeddings = DynamicEmbeddings(
                api_key_manager,
                api_key=default_embedding_api_key,
                base_url=default_embedding_base_url,
                model=default_embedding_model,
            )
            logger.info("使用 DynamicEmbeddings 初始化（支持用户自定义 Embedding Key）")
        else:
            # 无 ApiKeyManager 时使用默认 Embeddings（兼容现有逻辑）
            try:
                from langchain_community.embeddings import DashScopeEmbeddings
                self.embeddings = DashScopeEmbeddings(
                    dashscope_api_key=default_embedding_api_key,
                    model=default_embedding_model,
                )
                logger.info("使用 DashScopeEmbeddings 初始化成功")
            except ImportError:
                self.embeddings = OpenAIEmbeddings(
                    api_key=default_embedding_api_key,
                    base_url=default_embedding_base_url,
                    model=default_embedding_model,
                    check_embedding_ctx_length=False,
                )

        # 初始化向量存储
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=settings.chroma_persist_directory,
        )

        # 初始化 LLM（保留默认，实际聊天请求时由 chat.py 的 _get_llm 动态创建）
        self.llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
            temperature=0.5,
        )

        # 语义分块器
        self.chunker = SemanticChunker(
            target_size=getattr(settings, "chunk_target_size", 750),
            min_size=getattr(settings, "chunk_min_size", 300),
            max_size=getattr(settings, "chunk_max_size", 900),
            overlap=getattr(settings, "chunk_overlap", 100),
        )
    
    def add_video_content(
        self,
        video: VideoContent,
        page_index: int = 0,
        page_title: Optional[str] = None,
    ) -> int:
        """
        添加单个视频内容到向量库

        Args:
            video: VideoContent 对象
            page_index: 分P序号（0-based），默认 0
            page_title: 分P标题，默认 None

        Returns:
            添加的文档块数量
        """
        # 构建完整内容（正文不带标题，避免标题相似度主导召回）
        title = video.title or "未知标题"
        content_parts: List[str] = []
        
        if video.content and video.content.strip():
            content_parts.append(video.content.strip())
        
        # 如果有分段提纲，添加结构化信息
        if video.outline:
            outline_text = "\n## 内容提纲\n"
            for item in video.outline:
                item_title = item.get('title', '') or ''
                outline_text += f"\n### {item_title}\n"
                for point in item.get("points", []):
                    point_content = point.get('content', '') or ''
                    if point_content:
                        outline_text += f"- {point_content}\n"
            if outline_text.strip() != "## 内容提纲":
                content_parts.append(outline_text)
        
        full_content = "\n\n".join(content_parts).strip()

        # 验证内容不为空
        if not full_content or len(full_content.strip()) < 10:
            logger.warning(f"[{video.bvid}] 内容太少，跳过")
            return 0

        # 语义分块（Phase 1: 增强规则分块 + Phase 2: embedding 输入策略）
        chunk_results = self.chunker.chunk(
            text=full_content,
            video_title=title,
            page_title=page_title or title,
            outline=video.outline,
        )

        if not chunk_results:
            logger.warning(f"[{video.bvid}] 语义分块后无有效文档块")
            return 0

        # Phase 4: 可观测性 — 分块统计日志（供 LangSmith / 本地调试使用）
        chunk_lengths = [len(c.display_text) for c in chunk_results]
        logger.info(
            f"[VECTORIZE_TRACE] bvid={video.bvid} page={page_index} "
            f"raw_len={len(full_content)} chunk_count={len(chunk_results)} "
            f"avg_len={sum(chunk_lengths)//max(len(chunk_lengths),1)} "
            f"min_len={min(chunk_lengths)} max_len={max(chunk_lengths)} "
            f"has_outline={bool(video.outline)}"
        )

        # 创建文档（Phase 3: metadata 增强）
        embedding_version = getattr(settings, "embedding_version", "v1")
        documents = []
        for i, result in enumerate(chunk_results):
            chunk_id = f"{video.bvid}:{page_index}:{i}"
            doc = Document(
                page_content=result.embedding_text,  # 含标题前缀，用于 embedding + LLM 上下文
                metadata={
                    "bvid": video.bvid,
                    "title": title,
                    "page_index": page_index,
                    "page_title": page_title or title,
                    "source": video.source.value,
                    "chunk_index": i,
                    "chunk_id": chunk_id,
                    "section_title": result.section_title or "",
                    "content_type": result.content_type,
                    "embedding_version": embedding_version,
                    "url": f"https://www.bilibili.com/video/{video.bvid}?p={page_index + 1}",
                }
            )
            documents.append(doc)

        # 添加到向量库
        try:
            batch_size = 10
            for idx in range(0, len(documents), batch_size):
                self.vectorstore.add_documents(documents[idx:idx + batch_size])
            logger.info(
                f"[VECTORIZE_TRACE] bvid={video.bvid} page={page_index} "
                f"write_success=True chunks_written={len(documents)} "
                f"embedding_model={settings.embedding_model} "
                f"embedding_version={embedding_version}"
            )
        except Exception as e:
            logger.error(
                f"[VECTORIZE_TRACE] bvid={video.bvid} page={page_index} "
                f"write_success=False error={e}"
            )
            raise

        return len(documents)

    def _get_page_vector_ids(self, bvid: str, page_index: int) -> List[str]:
        """
        先按 bvid 获取全部 chunk，再在 Python 侧过滤 page_index，
        避免 Chroma 多条件 where 在不同版本下的兼容性问题。
        """
        result = self.vectorstore._collection.get(
            where={"bvid": bvid},
            include=["metadatas"]
        )
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        matched_ids: List[str] = []

        for doc_id, metadata in zip(ids, metadatas):
            if metadata and metadata.get("page_index") == page_index:
                matched_ids.append(doc_id)

        return matched_ids
    
    def add_videos_batch(self, videos: List[VideoContent], progress_callback=None) -> dict:
        """
        批量添加视频到向量库
        
        Args:
            videos: VideoContent 列表
            progress_callback: 进度回调 callback(current, total, title)
            
        Returns:
            {"success": 成功数, "failed": 失败数, "chunks": 总块数}
        """
        success = 0
        failed = 0
        total_chunks = 0
        
        for i, video in enumerate(videos):
            try:
                chunks = self.add_video_content(video)
                total_chunks += chunks
                success += 1
                
                if progress_callback:
                    progress_callback(i + 1, len(videos), video.title)
                    
            except Exception as e:
                logger.error(f"添加视频失败 [{video.bvid}]: {e}")
                failed += 1
        
        return {
            "success": success,
            "failed": failed,
            "chunks": total_chunks
        }
    
    def search(
        self,
        query: str,
        k: int = 5,
        bvids: Optional[List[str]] = None,
        workspace_pages: Optional[List[dict]] = None,
    ) -> List[Document]:
        """
        检索相关内容

        Args:
            query: 查询文本
            k: 召回数量
            bvids: 可选，限制在这些视频范围内搜索
            workspace_pages: 可选，工作区选中的分P列表，用于精确过滤。
                             格式: [{"bvid": "BVxxx", "cid": 123, "page_index": 0}, ...]
        """
        if not query or not query.strip():
            logger.warning("检索查询为空")
            return []

        try:
            # 构建过滤条件
            filter_cond = None
            if workspace_pages:
                # 工作区模式：精确匹配 bvid + page_index
                conditions = []
                for wp in workspace_pages:
                    bvid_val = wp.get("bvid")
                    page_idx = wp.get("page_index", 0)
                    # 诊断：检查是否有异常类型
                    if not isinstance(bvid_val, str):
                        logger.warning(f"[RAG_SEARCH_DEBUG] workspace_pages 中 bvid 类型异常: type={type(bvid_val)}, value={repr(bvid_val)[:50]}")
                    if not isinstance(page_idx, int):
                        logger.warning(f"[RAG_SEARCH_DEBUG] workspace_pages 中 page_index 类型异常: type={type(page_idx)}, value={repr(page_idx)[:50]}")
                    conditions.append({
                        "bvid": bvid_val,
                        "page_index": page_idx
                    })
                if conditions:
                    # Chroma 的 $or 需要用 where_document 配合
                    # 这里用简化的方式：先用 bvids 过滤，再在结果中过滤 page_index
                    try:
                        wp_bvids = list(set(wp.get("bvid") for wp in workspace_pages))
                    except TypeError as te:
                        logger.warning(f"[RAG_SEARCH_DEBUG] wp_bvids set 构建失败: {te}")
                        raise
                    filter_cond = {"bvid": {"$in": wp_bvids}}
            elif bvids:
                filter_cond = {"bvid": {"$in": bvids}}

            if filter_cond:
                docs = self.vectorstore.similarity_search(query, k=k, filter=filter_cond)
            else:
                docs = self.vectorstore.similarity_search(query, k=k)

            # 工作区模式：进一步按 page_index 精确过滤
            if workspace_pages:
                wp_set = {(wp.get("bvid"), wp.get("page_index", 0)) for wp in workspace_pages}
                docs = [d for d in docs if (d.metadata.get("bvid"), d.metadata.get("page_index", 0)) in wp_set]

            logger.info(f"检索完成：query='{query}'，召回={len(docs)}")
            for idx, doc in enumerate(docs):
                meta = doc.metadata or {}
                title = meta.get("title", "")
                bvid = meta.get("bvid", "")
                chunk_index = meta.get("chunk_index", "")
                preview = doc.page_content[:120].replace("\n", " ").strip()
                logger.info(f"召回[{idx+1}] {bvid} #{chunk_index} {title} | {preview}")

            return docs
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []
    
    async def _fallback_answer(self, question: str, reason: str = "", context: str = "") -> dict:
        """
        当没有检索到内容时，让 AI 自然回复

        Args:
            question: 用户问题
            reason: 原因说明
            context: 可选的收藏夹概览上下文

        Returns:
            回答结果
        """
        try:
            system_prompt = fallback_system_prompt(context=context, reason=reason)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ]
            response = await self.llm.ainvoke(messages)
            answer = str(response.content or "").strip()
            return {
                "answer": answer,
                "sources": []
            }
        except Exception as e:
            logger.error(f"Fallback 回复失败: {e}")
            return {
                "answer": f"抱歉，{reason}。您可以尝试构建更多收藏夹内容，或者换个问法试试。",
                "sources": []
            }

    async def answer_question(self, question: str, k: int = 5, bvids: Optional[List[str]] = None) -> dict:
        """
        回答问题
        
        Args:
            question: 用户问题
            k: 检索文档数量
            bvids: 可选，限制在这些视频范围内搜索
            
        Returns:
            {
                "answer": 回答内容,
                "sources": 来源视频列表
            }
        """
        # 先检查向量库是否有内容
        stats = self.get_collection_stats()
        if stats["total_chunks"] == 0:
            # 知识库为空时，使用 fallback 让 AI 自然回复
            return await self._fallback_answer(question, "知识库目前还没有内容")
        
        # 检索相关文档
        try:
            docs = self.search(question, k=k, bvids=bvids if bvids else None)
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return await self._fallback_answer(question, f"检索时遇到问题")
        
        if not docs:
            # 没检索到内容时，也让 AI 自然回复
            return await self._fallback_answer(question, "没有找到相关内容")
        
        # 构建上下文
        context_parts = []
        seen_bvids = set()
        sources = []
        
        for doc in docs:
            bvid = doc.metadata.get("bvid", "")
            title = doc.metadata.get("title", "未知标题")
            content = doc.page_content.strip()

            if not content:
                continue

            # page_content 现在已是 embedding_text（含标题前缀），
            # 但旧数据可能没有。做兼容：若内容不以标题开头则补标题。
            if not content.startswith(title):
                content = f"【{title}】\n{content}"

            context_parts.append(content)

            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                sources.append({
                    "bvid": bvid,
                    "title": title,
                    "url": doc.metadata.get("url", f"https://www.bilibili.com/video/{bvid}")
                })
        
        # 如果没有有效内容
        if not context_parts:
            return {
                "answer": "检索到了相关视频，但没有找到有效的文本内容。可能是视频还未完成内容提取。",
                "sources": sources
            }
        
        context = "\n\n---\n\n".join(context_parts)
        
        # 确保 context 不为空
        if not context.strip():
            return {
                "answer": "没有找到可用的内容来回答您的问题。",
                "sources": sources
            }
        
        # 构建消息并调用 LLM
        try:
            system_prompt = qa_system_prompt(context)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ]
            response = await self.llm.ainvoke(messages)
            answer = str(response.content or "").strip()

            return {
                "answer": answer,
                "sources": sources
            }
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                "answer": f"AI 回答时发生错误: {str(e)}",
                "sources": sources
            }
    
    async def summarize_content(self, content: str) -> str:
        """
        使用 LLM 总结内容（用于字幕内容）
        
        Args:
            content: 原始内容（字幕文本）
            
        Returns:
            总结后的内容
        """
        # 如果内容太长，先截断
        max_length = 10000
        if len(content) > max_length:
            content = content[:max_length] + "\n...(内容已截断)"
        
        system_prompt = summary_system_prompt()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content),
        ]
        response = await self.llm.ainvoke(messages)
        return str(response.content or "").strip()
    
    def get_collection_stats(self) -> dict:
        """
        获取向量库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            collection = self.vectorstore._collection
            count = collection.count()
            
            # 获取唯一视频数
            result = collection.get(include=["metadatas"])
            bvids = set()
            for meta in result.get("metadatas", []):
                if meta and "bvid" in meta:
                    bvids.add(meta["bvid"])
            
            return {
                "total_chunks": count,
                "total_videos": len(bvids),
                "collection_name": self.collection_name
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_chunks": 0,
                "total_videos": 0,
                "collection_name": self.collection_name
            }
    
    def clear_collection(self):
        """清空向量库"""
        try:
            self.vectorstore._collection.delete(where={})
            logger.info(f"已清空向量库: {self.collection_name}")
        except Exception as e:
            logger.error(f"清空向量库失败: {e}")
            raise
    
    def delete_video(self, bvid: str):
        """
        删除指定视频的所有文档块

        Args:
            bvid: 视频 BV 号
        """
        try:
            self.vectorstore._collection.delete(where={"bvid": bvid})
            logger.info(f"已删除视频: {bvid}")
        except Exception as e:
            logger.error(f"删除视频失败 [{bvid}]: {e}")
            raise

    def delete_page_vectors(self, bvid: str, page_index: int):
        """
        删除指定分P的所有文档块

        Args:
            bvid: 视频 BV 号
            page_index: 分P序号（0-based）
        """
        try:
            ids = self._get_page_vector_ids(bvid, page_index)
            if ids:
                self.vectorstore._collection.delete(ids=ids)
            logger.info(f"已删除分P向量: {bvid} P{page_index + 1}")
        except Exception as e:
            logger.error(f"删除分P向量失败 [{bvid} P{page_index + 1}]: {e}")
            raise

    def get_page_vector_count(self, bvid: str, page_index: int) -> int:
        """
        获取指定分P的向量块数量

        Args:
            bvid: 视频 BV 号
            page_index: 分P序号（0-based）

        Returns:
            向量块数量
        """
        try:
            return len(self._get_page_vector_ids(bvid, page_index))
        except Exception as e:
            logger.warning(f"获取分P向量数量失败 [{bvid} P{page_index + 1}]: {e}")
            return 0
