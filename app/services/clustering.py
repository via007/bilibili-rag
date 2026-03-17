"""
主题聚类服务

根据视频摘要进行主题聚类，支持 K-Means 和 HDBSCAN 算法
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from langchain.embeddings.base import Embeddings
from langchain_openai import ChatOpenAI

from app.services.llm_factory import get_embeddings_client, get_llm_client

# LLM 生成主题名称的提示词
TOPIC_NAME_PROMPT = """你是一个专业的视频内容分类专家。根据给定的视频标题列表，请进行深度分析：

## 视频标题列表
{titles}

## 分析任务

### 1. 主题识别
分析这些视频的共同主题，用一个简洁的主题名称概括。
- 主题名称：2-8个字
- 要准确反映视频内容的核心主题

### 2. 关键词提取
从标题中提取3-5个最能代表这个主题的关键词。
- 关键词应该是这个领域的核心概念
- 有助于理解视频的具体内容方向

### 3. 难度评估
判断这个主题整体的学习难度：
- beginner（入门）：基础概念、科普性质
- intermediate（进阶）：需要一定基础、有深度
- advanced（高级）：专业内容、复杂技术

## 输出要求

请严格按照以下JSON格式输出：

```json
{
    "topic_name": "主题名称",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "difficulty": "难度级别"
}
```

注意：
1. topic_name 要简洁有力，能准确概括主题
2. keywords 要有代表性，能帮助理解主题内容
3. difficulty 要客观评估，符合目标受众水平
4. 只输出JSON，不要有其他内容
"""


@dataclass
class VideoSummary:
    """视频摘要"""
    bvid: str
    title: str
    short_intro: str = ""
    key_points: List[str] = field(default_factory=list)
    target_audience: str = ""
    difficulty_level: str = "intermediate"  # beginner/intermediate/advanced
    tags: List[str] = field(default_factory=list)

    def to_embedding_text(self) -> str:
        """转换为用于 embedding 的文本"""
        parts = [self.title]
        if self.short_intro:
            parts.append(self.short_intro)
        if self.key_points:
            parts.extend(self.key_points)
        if self.tags:
            parts.extend(self.tags)
        return " ".join(parts)


@dataclass
class TopicCluster:
    """主题聚类"""
    cluster_id: int
    topic_name: str = ""
    video_count: int = 0
    videos: List[VideoSummary] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    difficulty_distribution: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def calculate_stats(self):
        """计算聚类统计数据"""
        self.video_count = len(self.videos)

        # 计算难度分布
        difficulty_dist: Dict[str, int] = {
            "beginner": 0,
            "intermediate": 0,
            "advanced": 0
        }
        for video in self.videos:
            level = video.difficulty_level or "intermediate"
            difficulty_dist[level] = difficulty_dist.get(level, 0) + 1
        self.difficulty_distribution = difficulty_dist

        # 提取关键词（从所有视频的 tags 中）
        all_tags: List[str] = []
        for video in self.videos:
            all_tags.extend(video.tags or [])
        # 去重并保留出现次数最多的
        tag_counts: Dict[str, int] = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        self.keywords = sorted(tag_counts.keys(), key=lambda x: tag_counts[x], reverse=True)[:10]


class TopicClusteringService:
    """主题聚类服务"""

    def __init__(
        self,
        embeddings: Optional[Embeddings] = None,
        llm: Optional[ChatOpenAI] = None
    ):
        """
        初始化聚类服务

        Args:
            embeddings: Embedding 客户端，默认使用配置的 embedding 模型
            llm: LLM 客户端，默认使用配置的 LLM 模型
        """
        self.embeddings = embeddings or get_embeddings_client()
        self.llm = llm or get_llm_client()

    async def cluster_videos(
        self,
        videos: List[VideoSummary],
        n_clusters: Optional[int] = None,
        min_cluster_size: int = 2,
        algorithm: str = "kmeans"
    ) -> List[TopicCluster]:
        """
        对视频进行主题聚类

        Args:
            videos: 视频摘要列表
            n_clusters: 聚类数量（仅 K-Means 有效）
            min_cluster_size: 最小聚类大小
            algorithm: 聚类算法 "kmeans" 或 "hdbscan"

        Returns:
            主题聚类列表
        """
        if len(videos) < min_cluster_size:
            return []

        # 1. 生成特征向量
        texts = [v.to_embedding_text() for v in videos]
        embeddings = self.embeddings.embed_documents(texts)

        # 2. 执行聚类
        if algorithm == "hdbscan":
            labels = self._hdbscan_cluster(embeddings, min_cluster_size)
        else:
            # 默认使用 K-Means
            if n_clusters is None:
                # 自动确定聚类数：平方根法则
                n_clusters = max(2, int(len(videos) ** 0.5))
            labels = self._kmeans_cluster(embeddings, n_clusters)

        # 3. 构建聚类结果
        clusters = self._build_clusters(videos, labels)

        # 4. 使用 LLM 生成主题名称
        clusters = await self._generate_topic_names(clusters)

        return clusters

    def _kmeans_cluster(
        self,
        embeddings: List[List[float]],
        n_clusters: int
    ) -> List[int]:
        """
        K-Means 聚类

        Args:
            embeddings: 特征向量列表
            n_clusters: 聚类数量

        Returns:
            每个视频对应的聚类标签
        """
        try:
            from sklearn.cluster import KMeans
        except ImportError:
            raise ImportError("请安装 scikit-learn: pip install scikit-learn")

        # 转换为 numpy 数组
        X = np.array(embeddings)

        # K-Means 聚类
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        return labels

    def _hdbscan_cluster(
        self,
        embeddings: List[List[float]],
        min_cluster_size: int
    ) -> List[int]:
        """
        HDBSCAN 聚类（自动确定聚类数）

        Args:
            embeddings: 特征向量列表
            min_cluster_size: 最小聚类大小

        Returns:
            每个视频对应的聚类标签
        """
        try:
            import hdbscan
        except ImportError:
            raise ImportError("请安装 hdbscan: pip install hdbscan")

        X = np.array(embeddings)

        # HDBSCAN 聚类
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric='cosine'
        )
        labels = clusterer.fit_predict(X)

        return labels

    def _build_clusters(
        self,
        videos: List[VideoSummary],
        labels: List[int]
    ) -> List[TopicCluster]:
        """
        构建聚类结果

        Args:
            videos: 视频列表
            labels: 聚类标签

        Returns:
            主题聚类列表
        """
        # 按标签分组
        cluster_map: Dict[int, List[VideoSummary]] = {}
        for video, label in zip(videos, labels):
            if label not in cluster_map:
                cluster_map[label] = []
            cluster_map[label].append(video)

        # 构建 TopicCluster 列表
        clusters = []
        for cluster_id, cluster_videos in cluster_map.items():
            cluster = TopicCluster(
                cluster_id=cluster_id,
                videos=cluster_videos
            )
            cluster.calculate_stats()
            clusters.append(cluster)

        # 按视频数量降序排序
        clusters.sort(key=lambda x: x.video_count, reverse=True)

        # 重新编号
        for i, cluster in enumerate(clusters):
            cluster.cluster_id = i

        return clusters

    async def _generate_topic_names(
        self,
        clusters: List[TopicCluster]
    ) -> List[TopicCluster]:
        """
        使用 LLM 为每个聚类生成主题名称

        Args:
            clusters: 聚类列表

        Returns:
            带主题名称的聚类列表
        """
        for cluster in clusters:
            if not cluster.videos:
                continue

            # 提取视频标题（最多 8 个）
            titles = [v.title for v in cluster.videos[:8]]

            # 构建提示词
            prompt = TOPIC_NAME_PROMPT.format(titles="\n".join(f"- {t}" for t in titles))

            try:
                # 调用 LLM 生成主题名称
                response = await self.llm.agenerate([prompt])
                topic_name = response.generations[0][0].text.strip()

                # 清理主题名称（去除引号等）
                topic_name = topic_name.strip('"\'「」')
                cluster.topic_name = topic_name
            except Exception as e:
                # 如果 LLM 调用失败，使用默认名称
                cluster.topic_name = f"主题 {cluster.cluster_id + 1}"

        return clusters


# 服务实例缓存
_clustering_service: Optional[TopicClusteringService] = None


def get_clustering_service() -> TopicClusteringService:
    """获取聚类服务实例（单例）"""
    global _clustering_service
    if _clustering_service is None:
        _clustering_service = TopicClusteringService()
    return _clustering_service
