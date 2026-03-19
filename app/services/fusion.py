"""
结果融合服务 - Reciprocal Rank Fusion (RRF)

将多路召回结果进行融合，使用 RRF 算法综合排名
"""
from typing import List, Dict, Any
from dataclasses import dataclass, field
from loguru import logger
from langchain_core.documents import Document


@dataclass
class RetrievedDoc:
    """单路召回的检索文档"""
    doc: Document
    score: float  # 该路召回的分数 (如相似度、BM25分数等)
    rank: int  # 在该路召回中的排名 (1, 2, 3...)
    source: str  # 来源标识: "vector" | "keyword" | "time"


class ResultFusion:
    """结果融合器 - Reciprocal Rank Fusion"""

    @staticmethod
    def fuse(results_list: List[List[RetrievedDoc]], k: int = 60) -> List[Any]:
        """
        RRF 融合

        公式: RRF_score(d) = Σ 1 / (rank(d) + k)

        Args:
            results_list: 三路召回结果列表 [vector_results, keyword_results, time_results]
            k: RRF 参数 (默认 60)

        Returns:
            融合后的结果列表 (返回 FusedRetrievedDoc 类型的列表)
        """
        if not results_list:
            logger.warning("融合结果为空列表")
            return []

        # 统计各路召回数量
        for i, results in enumerate(results_list):
            source_name = ["vector", "keyword", "time"][i] if i < 3 else f"source_{i}"
            logger.debug(f"{source_name} 召回 {len(results)} 条")

        # 用于存储每个文档的 RRF 分数和来源信息
        # key: doc_id (bvid + chunk_index)
        # value: {doc, rrf_score, sources}
        doc_scores: Dict[str, Dict[str, Any]] = {}

        # 遍历每一路召回结果
        for results in results_list:
            if not results:
                continue

            source = results[0].source if results else "unknown"

            for retrieved_doc in results:
                # 生成文档唯一标识
                doc_id = ResultFusion._get_doc_id(retrieved_doc.doc)

                if doc_id not in doc_scores:
                    doc_scores[doc_id] = {
                        "doc": retrieved_doc.doc,
                        "rrf_score": 0.0,
                        "sources": []
                    }

                # 累加 RRF 分数: score += 1 / (rank + k)
                rrf_contribution = 1.0 / (retrieved_doc.rank + k)
                doc_scores[doc_id]["rrf_score"] += rrf_contribution

                # 记录来源
                if source not in doc_scores[doc_id]["sources"]:
                    doc_scores[doc_id]["sources"].append(source)

        if not doc_scores:
            logger.warning("融合后无结果")
            return []

        # 按 RRF 分数排序 (降序)
        sorted_docs = sorted(
            doc_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        # 构建返回结果
        # 注意: 为了兼容 reranker.py，使用 score 字段而非 rrf_score
        from app.services.reranker import FusedRetrievedDoc

        fused_results = []
        for rank, item in enumerate(sorted_docs, 1):
            fused_results.append(FusedRetrievedDoc(
                doc=item["doc"],
                score=item["rrf_score"],  # 使用 score 字段兼容 reranker
                rank=rank,
                sources=item["sources"]
            ))
            logger.debug(
                f"融合结果[{rank}] RRF_score={item['rrf_score']:.4f} "
                f"bvid={item['doc'].metadata.get('bvid', '')} "
                f"sources={item['sources']}"
            )

        logger.info(f"RRF 融合完成: {len(fused_results)} 条结果")
        return fused_results

    @staticmethod
    def _get_doc_id(doc: Document) -> str:
        """
        生成文档唯一标识

        使用 bvid + chunk_index 作为唯一标识
        """
        bvid = doc.metadata.get("bvid", "")
        chunk_index = doc.metadata.get("chunk_index", 0)
        return f"{bvid}_{chunk_index}"


def create_fusion() -> ResultFusion:
    """
    工厂函数：创建结果融合器实例

    Returns:
        ResultFusion 实例
    """
    return ResultFusion()
