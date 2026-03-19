"""
Cross-Encoder 重排序服务

使用 sentence-transformers 的 CrossEncoder 对检索结果进行精确排序

重排序提示词说明：
- Cross-Encoder 会计算 query 和 candidate 文档之间的相关性分数
- 分数越高表示文档与问题越相关
- 重排序后，Top-K 结果将作为最终问答的上下文输入
"""
from typing import List
from dataclasses import dataclass
from loguru import logger
from langchain_core.documents import Document


@dataclass
class FusedRetrievedDoc:
    """RRF 融合后的检索文档"""
    doc: Document
    score: float  # RRF 融合分数
    rank: int  # 排名
    sources: List[str]  # 来源标识 ["vector", "keyword", "time"]


@dataclass
class RerankedDoc:
    """重排序后的文档"""
    doc: Document
    score: float  # Cross-Encoder 分数
    rank: int  # 重排序后的排名
    sources: List[str]  # 保留来源信息


class CrossEncoderReranker:
    """Cross-Encoder 重排序器"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        """
        初始化重排序器

        Args:
            model_name: HuggingFace 模型名称
                推荐:
                - BAAI/bge-reranker-base (中文效果好)
                - BAAI/bge-reranker-large
                - cross-encoder/ms-marco-MiniLM-L-6-v2
        """
        self.model_name = model_name
        self._model = None
        logger.info(f"初始化 Cross-Encoder 重排序器: {model_name}")

    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Cross-Encoder 模型加载成功: {self.model_name}")
            except ImportError as e:
                logger.error(f"请安装 sentence-transformers: pip install sentence-transformers")
                raise ImportError("需要安装 sentence-transformers") from e
            except Exception as e:
                logger.error(f"Cross-Encoder 模型加载失败: {e}")
                raise
        return self._model

    def rerank(
        self,
        query: str,
        candidates: List[FusedRetrievedDoc],
        top_k: int = 5
    ) -> List[RerankedDoc]:
        """
        重排序

        流程：
        1. 构造 query-doc 对 [query, title + content]
        2. 批量预测分数
        3. 按分数排序返回 top_k

        Args:
            query: 用户问题
            candidates: RRF 融合后的候选文档
            top_k: 返回数量

        Returns:
            reranked: 重排序后的结果
        """
        if not candidates:
            logger.warning("候选文档为空，跳过重排序")
            return []

        if len(candidates) <= 1:
            # 只有一个候选，不需要重排序
            return [
                RerankedDoc(
                    doc=candidates[0].doc,
                    score=1.0,
                    rank=1,
                    sources=candidates[0].sources
                )
            ]

        # 1. 构造查询-文档对
        pairs = []
        for cand in candidates:
            # 拼接标题和内容
            title = cand.doc.metadata.get("title", "")
            content = cand.doc.page_content
            # 组合标题和内容作为输入
            text = f"{title}\n{content}" if title else content
            pairs.append([query, text])

        # 2. 批量预测分数
        try:
            scores = self.model.predict(pairs)
            logger.info(f"Cross-Encoder 预测完成: {len(scores)} 个候选")
        except Exception as e:
            logger.error(f"Cross-Encoder 预测失败: {e}")
            # 预测失败时返回原始顺序
            return [
                RerankedDoc(
                    doc=cand.doc,
                    score=cand.score,
                    rank=idx + 1,
                    sources=cand.sources
                )
                for idx, cand in enumerate(candidates[:top_k])
            ]

        # 3. 按分数排序并返回 Top-K
        reranked = []
        sorted_results = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True
        )

        for rank, (cand, score) in enumerate(sorted_results[:top_k], 1):
            reranked.append(RerankedDoc(
                doc=cand.doc,
                score=float(score),
                rank=rank,
                sources=cand.sources
            ))
            logger.debug(
                f"重排序[{rank}] score={score:.4f} "
                f"bvid={cand.doc.metadata.get('bvid', '')} "
                f"sources={cand.sources}"
            )

        return reranked


def create_reranker(model_name: str = "BAAI/bge-reranker-base") -> CrossEncoderReranker:
    """
    工厂函数：创建重排序器实例

    Args:
        model_name: 模型名称

    Returns:
        CrossEncoderReranker 实例
    """
    return CrossEncoderReranker(model_name=model_name)
