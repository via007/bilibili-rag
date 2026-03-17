"""
Bilibili RAG 知识库系统

多路召回服务 - Vector + Keyword + Time 三路召回 + RRF 融合

三路召回策略：
1. Vector Search: 向量语义相似度检索
2. Keyword Search: BM25 关键词精确匹配检索
3. Time Search: 按视频入库时间排序

融合算法: RRF (Reciprocal Rank Fusion)
"""
from typing import List, Dict, Tuple, Optional
from loguru import logger
from sqlalchemy import select, desc, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.documents import Document
from app.models import VideoCache
from app.services.rag import RAGService
from app.services.retrievers import KeywordRetriever, TimeRetriever
from app.database import async_session_factory


# RRF 常量
RRF_K = 60  # RRF 算法中的常数


class MultiRecallService:
    """
    多路召回服务

    整合向量检索、关键词检索、时间排序三种召回策略，
    使用 RRF 算法融合结果。
    """

    def __init__(self, collection_name: str = "bilibili_videos"):
        self.rag_service = RAGService(collection_name)
        self.collection_name = collection_name
        # 初始化 BM25 关键词检索器
        self.keyword_retriever = KeywordRetriever(k1=1.5, b=0.75)
        # 初始化时间检索器
        self.time_retriever = TimeRetriever(lambda_decay=0.1)

    async def search(
        self,
        query: str,
        k: int = 5,
        bvids: Optional[List[str]] = None,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.5,
        time_weight: float = 0.2,
        enable_keyword: bool = True,
        enable_time: bool = True,
    ) -> Tuple[List[Document], Dict]:
        """
        多路召回搜索

        Args:
            query: 检索查询
            k: 返回结果数量
            bvids: 限制检索的视频BV列表
            keyword_weight: 关键词检索权重
            vector_weight: 向量检索权重
            time_weight: 时间排序权重
            enable_keyword: 是否启用关键词检索
            enable_time: 是否启用时间排序

        Returns:
            (召回的文档列表, 各路召回的详细信息)
        """
        if not query or not query.strip():
            logger.warning("检索查询为空")
            return [], {"error": "查询为空"}

        # 并行执行三路召回
        vector_docs = await self._vector_search(query, k * 3, bvids)

        keyword_docs = []
        if enable_keyword:
            keyword_docs = await self._keyword_search(query, k * 3, bvids)

        time_docs = []
        if enable_time:
            time_docs = await self._time_search(query, k * 3, bvids)

        # RRF 融合
        fused_docs = self._rrf_fusion(
            vector_docs,
            keyword_docs,
            time_docs,
            keyword_weight,
            vector_weight,
            time_weight,
            k
        )

        # 记录日志
        recall_info = {
            "query": query,
            "vector_count": len(vector_docs),
            "keyword_count": len(keyword_docs),
            "time_count": len(time_docs),
            "fused_count": len(fused_docs),
            "weights": {
                "keyword": keyword_weight,
                "vector": vector_weight,
                "time": time_weight
            }
        }

        logger.info(
            f"多路召回完成: query='{query}', "
            f"vector={len(vector_docs)}, keyword={len(keyword_docs)}, "
            f"time={len(time_docs)}, fused={len(fused_docs)}"
        )

        return fused_docs, recall_info

    async def _vector_search(
        self,
        query: str,
        k: int,
        bvids: Optional[List[str]] = None
    ) -> List[Document]:
        """
        向量检索

        使用 ChromaDB 进行语义相似度搜索
        """
        try:
            if bvids:
                docs = self.rag_service.vectorstore.similarity_search(
                    query, k=k, filter={"bvid": {"$in": bvids}}
                )
            else:
                docs = self.rag_service.vectorstore.similarity_search(query, k=k)

            logger.debug(f"向量检索召回: {len(docs)}")
            return docs
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    async def _keyword_search(
        self,
        query: str,
        k: int,
        bvids: Optional[List[str]] = None
    ) -> List[Document]:
        """
        关键词检索 (BM25)

        使用 BM25 算法进行关键词匹配检索
        """
        try:
            # 获取候选文档
            if bvids:
                candidate_docs = self.rag_service.vectorstore.similarity_search(
                    query, k=k * 5, filter={"bvid": {"$in": bvids}}
                )
            else:
                candidate_docs = self.rag_service.vectorstore.similarity_search(
                    query, k=k * 5
                )

            if not candidate_docs:
                return []

            # 使用 BM25 算法进行检索
            results = self.keyword_retriever.retrieve(
                query=query,
                documents=candidate_docs,
                top_k=k
            )

            matched_docs = [r.doc for r in results]

            logger.debug(f"关键词检索(BM25)召回: {len(matched_docs)}")
            return matched_docs

        except Exception as e:
            logger.warning(f"关键词检索失败: {e}")
            return []

    async def _time_search(
        self,
        query: str,
        k: int,
        bvids: Optional[List[str]] = None
    ) -> List[Document]:
        """
        时间排序检索

        按视频入库时间排序，优先返回最新入库的内容
        使用时间衰减算法计算分数
        """
        try:
            # 从数据库获取按时间排序的视频
            async with async_session_factory() as db:
                stmt = (
                    select(VideoCache)
                    .where(VideoCache.is_processed == True)
                    .order_by(desc(VideoCache.created_at))
                )

                if bvids:
                    stmt = stmt.where(VideoCache.bvid.in_(bvids))

                stmt = stmt.limit(k * 3)
                result = await db.execute(stmt)
                videos = result.scalars().all()

            # 获取这些视频的文档
            video_bvids = [v.bvid for v in videos]

            if not video_bvids:
                return []

            # 从向量库获取这些视频的文档
            all_docs = self.rag_service.vectorstore.get(
                where={"bvid": {"$in": video_bvids}},
                include=["documents", "metadatas"]
            )

            # 构建文档列表，添加 created_at 到 metadata
            docs = []
            video_created_at = {v.bvid: v.created_at.isoformat() if v.created_at else None for v in videos}

            for bvid in video_bvids:
                if all_docs and "documents" in all_docs:
                    for i, doc_bvid in enumerate(all_docs.get("metadatas", [])):
                        if doc_bvid.get("bvid") == bvid:
                            metadata = dict(all_docs["metadatas"][i])
                            # 添加 created_at 用于时间排序
                            metadata["created_at"] = video_created_at.get(bvid)
                            doc = Document(
                                page_content=all_docs["documents"][i],
                                metadata=metadata
                            )
                            docs.append(doc)
                            break

            # 使用时间检索器排序
            results = self.time_retriever.retrieve(documents=docs, top_k=k)

            logger.debug(f"时间排序召回: {len(results)}")
            return [r.doc for r in results]

        except Exception as e:
            logger.warning(f"时间排序检索失败: {e}")
            return []

    def _rrf_fusion(
        self,
        vector_docs: List[Document],
        keyword_docs: List[Document],
        time_docs: List[Document],
        keyword_weight: float,
        vector_weight: float,
        time_weight: float,
        k: int
    ) -> List[Document]:
        """
        RRF 融合

        使用加权 RRF 算法融合三路召回结果
        """
        # 计算每路检索中每个文档的排名得分
        doc_scores: Dict[str, float] = {}

        # 向量检索得分
        for rank, doc in enumerate(vector_docs):
            doc_key = self._get_doc_key(doc)
            score = vector_weight * (1 / (RRF_K + rank + 1))
            doc_scores[doc_key] = doc_scores.get(doc_key, 0) + score

        # 关键词检索得分
        for rank, doc in enumerate(keyword_docs):
            doc_key = self._get_doc_key(doc)
            score = keyword_weight * (1 / (RRF_K + rank + 1))
            doc_scores[doc_key] = doc_scores.get(doc_key, 0) + score

        # 时间排序得分
        for rank, doc in enumerate(time_docs):
            doc_key = self._get_doc_key(doc)
            score = time_weight * (1 / (RRF_K + rank + 1))
            doc_scores[doc_key] = doc_scores.get(doc_key, 0) + score

        # 按得分排序，取 top k
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        # 构建最终文档列表
        result_docs = []
        doc_map = {self._get_doc_key(d): d for d in vector_docs + keyword_docs + time_docs}

        for doc_key, score in sorted_docs[:k]:
            if doc_key in doc_map:
                doc = doc_map[doc_key]
                # 添加来源信息
                if not hasattr(doc, 'metadata'):
                    doc.metadata = {}
                doc.metadata['_rrf_score'] = score
                result_docs.append(doc)

        return result_docs

    def _get_doc_key(self, doc: Document) -> str:
        """
        生成文档唯一键

        使用 bvid 和 chunk_index 作为唯一标识
        """
        meta = doc.metadata or {}
        bvid = meta.get("bvid", "")
        chunk_index = meta.get("chunk_index", 0)
        return f"{bvid}_{chunk_index}"


# 导出
__all__ = ["MultiRecallService", "RRF_K"]
