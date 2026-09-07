"""
Bilibili RAG 知识库系统

RAG 服务模块 - 向量存储与问答
"""
from typing import Callable, List, Optional
from loguru import logger
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from app.config import settings
from app.models import VideoContent
from app.services.cancellation import OperationCancelled, ensure_not_cancelled


class RAGService:
    """
    RAG 服务
    
    负责：
    1. 向量存储管理
    2. 文档添加与检索
    """
    
    def __init__(self, collection_name: str = "bilibili_videos"):
        """
        初始化 RAG 服务
        
        Args:
            collection_name: 向量集合名称
        """
        self.collection_name = collection_name
        
        # 初始化 Embeddings (使用 DashScope 原生支持)
        try:
            from langchain_community.embeddings import DashScopeEmbeddings
        except ImportError as exc:
            logger.error("缺少 langchain-community，无法初始化 DashScope Embedding")
            raise RuntimeError(
                "DashScope Embedding 初始化失败，请运行 pip install -r requirements.txt"
            ) from exc

        self.embeddings = DashScopeEmbeddings(
            dashscope_api_key=settings.openai_api_key,
            model=settings.embedding_model
        )
        logger.info("使用 DashScopeEmbeddings 初始化成功")
        
        # 初始化向量存储
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=settings.chroma_persist_directory
        )
        
        # 文本分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "]
        )
        
    def _build_metadata_document(self, video: VideoContent) -> Optional[Document]:
        """Build a compact searchable metadata document for title/intro recall."""
        parts = [f"视频标题：{video.title or '未知标题'}"]
        if video.owner_name:
            parts.append(f"UP主：{video.owner_name}")
        if video.description:
            parts.append(f"视频简介：{video.description}")
        if video.duration:
            parts.append(f"视频时长：{video.duration} 秒")
        if video.outline:
            outline_titles = []
            for item in video.outline:
                title = (item.get("title") or "").strip() if isinstance(item, dict) else ""
                if title:
                    outline_titles.append(title)
            if outline_titles:
                parts.append("内容提纲：" + "；".join(outline_titles[:8]))

        content = "\n".join(part for part in parts if part).strip()
        if len(content) < 10:
            return None

        return Document(
            page_content=content,
            metadata={
                "bvid": video.bvid,
                "title": video.title or "未知标题",
                "source": video.source.value,
                "doc_type": "metadata",
                "chunk_index": -1,
                "url": f"https://www.bilibili.com/video/{video.bvid}",
            },
        )
    
    def add_video_content(
        self,
        video: VideoContent,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> int:
        """
        添加单个视频内容到向量库
        
        Args:
            video: VideoContent 对象
            
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
        
        # 分块
        chunks = self.text_splitter.split_text(full_content)
        
        if not chunks:
            logger.warning(f"[{video.bvid}] 没有生成文档块")
            return 0
        
        # 过滤空内容块
        valid_chunks = [c for c in chunks if c and c.strip() and len(c.strip()) > 5]
        if not valid_chunks:
            logger.warning(f"[{video.bvid}] 没有有效的文档块")
            return 0
        
        # 创建文档。额外加入一条元信息文档，提升标题/简介/UP主类问题召回率。
        documents = []
        metadata_doc = self._build_metadata_document(video)
        if metadata_doc:
            documents.append(metadata_doc)

        for i, chunk in enumerate(valid_chunks):
            doc = Document(
                page_content=chunk.strip(),  # 确保是干净的字符串
                metadata={
                    "bvid": video.bvid,
                    "title": title,
                    "source": video.source.value,
                    "doc_type": "chunk",
                    "chunk_index": i,
                    "url": f"https://www.bilibili.com/video/{video.bvid}"
                }
            )
            documents.append(doc)
        
        # 添加到向量库
        added_ids: List[str] = []
        try:
            batch_size = 10
            for idx in range(0, len(documents), batch_size):
                ensure_not_cancelled(cancel_check)
                added_ids.extend(self.vectorstore.add_documents(documents[idx:idx + batch_size]))
                ensure_not_cancelled(cancel_check)
            logger.info(f"[{video.bvid}] 添加了 {len(documents)} 个文档块")
        except OperationCancelled:
            if added_ids:
                try:
                    self.vectorstore._collection.delete(ids=added_ids)
                except Exception as cleanup_error:
                    logger.error(f"[{video.bvid}] 取消后清理向量失败: {cleanup_error}")
            raise
        except Exception as e:
            logger.error(f"[{video.bvid}] 添加到向量库失败: {e}")
            if added_ids:
                try:
                    self.vectorstore._collection.delete(ids=added_ids)
                    logger.warning(f"[{video.bvid}] 已清理 {len(added_ids)} 个未完成向量")
                except Exception as cleanup_error:
                    logger.error(f"[{video.bvid}] 清理未完成向量失败: {cleanup_error}")
            raise
        
        return len(documents)
    
    def search(
        self,
        query: str,
        k: int = 5,
        bvids: Optional[List[str]] = None,
        fetch_k: Optional[int] = None,
        use_mmr: bool = True,
    ) -> List[Document]:
        """
        检索相关内容
        """
        if not query or not query.strip():
            logger.warning("检索查询为空")
            return []
            
        try:
            requested_k = max(1, k)
            candidate_k = max(fetch_k or settings.retrieval_mmr_fetch_k, requested_k)
            search_filter = {"bvid": {"$in": bvids}} if bvids else None
            docs: List[Document] = []

            if use_mmr:
                try:
                    docs = self.vectorstore.max_marginal_relevance_search(
                        query,
                        k=requested_k,
                        fetch_k=candidate_k,
                        lambda_mult=settings.retrieval_mmr_lambda,
                        filter=search_filter,
                    )
                except Exception as e:
                    logger.warning(f"MMR 检索失败，降级 similarity_search: {e}")

            if not docs:
                if search_filter:
                    docs = self.vectorstore.similarity_search(query, k=requested_k, filter=search_filter)
                else:
                    docs = self.vectorstore.similarity_search(query, k=requested_k)

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
            logger.error(f"向量检索失败: {e}")
            raise RuntimeError("向量检索失败") from e
    
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
    
    def has_video(self, bvid: str) -> bool:
        """检查指定视频是否实际存在于向量库。"""
        try:
            result = self.vectorstore._collection.get(where={"bvid": bvid}, limit=1)
            return bool(result.get("ids"))
        except Exception as e:
            logger.error(f"查询视频向量失败 [{bvid}]: {e}")
            raise RuntimeError(f"查询视频向量失败 [{bvid}]") from e

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
