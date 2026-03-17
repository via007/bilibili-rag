"""
多路召回检索器

实现 BM25 关键词检索和时间排序检索器
"""
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set

from langchain_core.documents import Document
from loguru import logger


@dataclass
class RetrievedDoc:
    """检索结果文档"""
    doc: Document
    score: float
    rank: int
    source: str  # "keyword" 或 "time"


class KeywordRetriever:
    """
    BM25 关键词检索器

    BM25 公式:
    Score = Σ IDF(qi) * (f(qi, D) * (k1 + 1)) / (f(qi, D) + k1 * (1 - b + b * |D| / avgdl))

    参数:
        k1 = 1.5
        b = 0.75
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def extract_keywords(self, text: str) -> Set[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            关键词集合
        """
        if not text:
            return set()

        # 简单的中文分词：按标点和空格分割，保留长度>=2的词
        # 去除标点符号
        text = re.sub(r'[，。！？、；：""''【】（）\s,.!?;:\[\]\(\)\{\}]+', ' ', text)

        # 提取连续的中文/英文/数字序列
        tokens = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+|\d+', text)

        # 过滤停用词和短词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
                     '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
                     '自己', '这', '那', '他', '她', '它', '们', '这个', '那个', '什么', '怎么',
                     'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
                     'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought', 'used'}

        keywords = {t for t in tokens if len(t) >= 2 and t.lower() not in stopwords}
        return keywords

    def _calculate_idf(self, doc_count: int, doc_freq: int) -> float:
        """
        计算 IDF

        简化版本: log(N)

        Args:
            doc_count: 文档总数
            doc_freq: 包含关键词的文档数

        Returns:
            IDF 值
        """
        if doc_freq == 0:
            return 0
        return math.log(doc_count)

    def _tokenize(self, text: str) -> List[str]:
        """
        将文本分词为词列表

        Args:
            text: 输入文本

        Returns:
            词列表
        """
        if not text:
            return []

        # 去除标点
        text = re.sub(r'[，。！？、；：""''【】（）\s,.!?;:\[\]\(\)\{\}]+', ' ', text)
        tokens = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+|\d+', text)
        return [t.lower() for t in tokens if len(t) >= 1]

    def _get_doc_term_freq(self, doc: Document) -> dict:
        """
        获取文档的词频

        Args:
            doc: 文档

        Returns:
            词频字典 {word: count}
        """
        tokens = self._tokenize(doc.page_content)
        term_freq = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
        return term_freq

    def calculate_score(
        self,
        query_keywords: Set[str],
        doc: Document,
        doc_count: int,
        avg_doc_length: float
    ) -> float:
        """
        计算 BM25 分数

        Args:
            query_keywords: 查询关键词集合
            doc: 文档
            doc_count: 文档总数
            avg_doc_length: 平均文档长度

        Returns:
            BM25 分数
        """
        if not query_keywords:
            return 0.0

        term_freq = self._get_doc_term_freq(doc)
        doc_length = sum(term_freq.values())

        score = 0.0
        for keyword in query_keywords:
            # 简化 IDF
            idf = math.log(doc_count + 1)

            # 词频
            tf = term_freq.get(keyword.lower(), 0)

            if tf == 0:
                continue

            # BM25 公式
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / avg_doc_length)

            if denominator > 0:
                score += idf * numerator / denominator

        return score

    def retrieve(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[RetrievedDoc]:
        """
        检索文档

        Args:
            query: 查询文本
            documents: 候选文档列表
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        if not query or not documents:
            return []

        # 提取查询关键词
        query_keywords = self.extract_keywords(query)
        logger.debug(f"查询关键词: {query_keywords}")

        if not query_keywords:
            return []

        # 计算平均文档长度
        doc_lengths = [sum(self._get_doc_term_freq(doc).values()) for doc in documents]
        avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1

        # 计算每个文档的 BM25 分数
        scores = []
        for doc in documents:
            score = self.calculate_score(
                query_keywords,
                doc,
                len(documents),
                avg_doc_length
            )
            if score > 0:
                scores.append((doc, score))

        # 按分数排序
        scores.sort(key=lambda x: x[1], reverse=True)

        # 取 top_k
        results = []
        for rank, (doc, score) in enumerate(scores[:top_k], 1):
            results.append(RetrievedDoc(
                doc=doc,
                score=score,
                rank=rank,
                source="keyword"
            ))

        logger.info(f"BM25 检索完成: 查询='{query}', 召回={len(results)}")
        return results


class TimeRetriever:
    """
    时间排序检索器

    按视频发布时间排序，使用指数衰减计算时间分数
    分数公式: score = exp(-λ * days)

    参数:
        lambda_decay: 衰减系数，默认 0.1
    """

    def __init__(self, lambda_decay: float = 0.1):
        self.lambda_decay = lambda_decay

    def _get_days_since(self, created_at_str: str) -> Optional[float]:
        """
        计算距离当前的天数

        Args:
            created_at_str: ISO 格式的时间字符串

        Returns:
            天数，如果无法解析则返回 None
        """
        if not created_at_str:
            return None

        try:
            # 尝试解析 ISO 格式
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                created_at = created_at_str

            # 计算天数差
            now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
            delta = now - created_at
            return delta.total_seconds() / 86400  # 转换为天
        except Exception as e:
            logger.warning(f"无法解析时间 '{created_at_str}': {e}")
            return None

    def calculate_score(self, created_at_str: str) -> float:
        """
        计算时间分数

        Args:
            created_at_str: 创建时间字符串

        Returns:
            时间分数 (0-1)
        """
        days = self._get_days_since(created_at_str)
        if days is None:
            return 0.0

        # 指数衰减
        score = math.exp(-self.lambda_decay * days)
        return score

    def retrieve(
        self,
        documents: List[Document],
        top_k: int = 5
    ) -> List[RetrievedDoc]:
        """
        检索文档（按时间排序）

        Args:
            documents: 候选文档列表
            top_k: 返回结果数量

        Returns:
            检索结果列表（按时间分数排序）
        """
        if not documents:
            return []

        # 计算每个文档的时间分数
        scored_docs = []
        for doc in documents:
            # 尝试从 metadata 获取 created_at
            created_at = doc.metadata.get("created_at")
            score = self.calculate_score(created_at) if created_at else 0.0

            if score > 0:
                scored_docs.append((doc, score))

        # 按时间分数排序（越新分数越高）
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # 取 top_k
        results = []
        for rank, (doc, score) in enumerate(scored_docs[:top_k], 1):
            results.append(RetrievedDoc(
                doc=doc,
                score=score,
                rank=rank,
                source="time"
            ))

        logger.info(f"时间检索完成: 召回={len(results)}")
        return results


class MultiRetriever:
    """
    多路召回器

    组合向量检索、关键词检索和时间排序
    """

    def __init__(
        self,
        keyword_k1: float = 1.5,
        keyword_b: float = 0.75,
        time_lambda: float = 0.1
    ):
        self.keyword_retriever = KeywordRetriever(k1=keyword_k1, b=keyword_b)
        self.time_retriever = TimeRetriever(lambda_decay=time_lambda)

    def keyword_search(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[RetrievedDoc]:
        """关键词检索"""
        return self.keyword_retriever.retrieve(query, documents, top_k)

    def time_search(
        self,
        documents: List[Document],
        top_k: int = 5
    ) -> List[RetrievedDoc]:
        """时间检索"""
        return self.time_retriever.retrieve(documents, top_k)

    def multi_search(
        self,
        query: str,
        documents: List[Document],
        keyword_weight: float = 0.7,
        time_weight: float = 0.3,
        top_k: int = 5
    ) -> List[RetrievedDoc]:
        """
        多路召回

        Args:
            query: 查询文本
            documents: 候选文档列表
            keyword_weight: 关键词权重
            time_weight: 时间权重
            top_k: 返回结果数量

        Returns:
            合并排序后的检索结果
        """
        if not documents:
            return []

        # 分别检索
        keyword_results = self.keyword_search(query, documents, top_k * 2)
        time_results = self.time_search(documents, top_k * 2)

        # 归一化分数
        max_keyword_score = max((r.score for r in keyword_results), default=1)
        max_time_score = max((r.score for r in time_results), default=1)

        # 合并结果
        combined_scores = {}
        for r in keyword_results:
            doc_id = id(r.doc)
            norm_score = r.score / max_keyword_score if max_keyword_score > 0 else 0
            combined_scores[doc_id] = {
                "doc": r.doc,
                "score": norm_score * keyword_weight,
                "source": ["keyword"]
            }

        for r in time_results:
            doc_id = id(r.doc)
            norm_score = r.score / max_time_score if max_time_score > 0 else 0
            if doc_id in combined_scores:
                combined_scores[doc_id]["score"] += norm_score * time_weight
                combined_scores[doc_id]["source"].append("time")
            else:
                combined_scores[doc_id] = {
                    "doc": r.doc,
                    "score": norm_score * time_weight,
                    "source": ["time"]
                }

        # 按综合分数排序
        sorted_results = sorted(
            combined_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )

        # 取 top_k
        results = []
        for rank, (doc_id, data) in enumerate(sorted_results[:top_k], 1):
            results.append(RetrievedDoc(
                doc=data["doc"],
                score=data["score"],
                rank=rank,
                source=",".join(data["source"])
            ))

        logger.info(f"多路召回完成: 查询='{query}', 召回={len(results)}")
        return results
