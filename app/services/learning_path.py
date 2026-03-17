"""
学习路径推荐服务

基于主题聚类和视频难度级别，推荐学习顺序。
"""
from collections import defaultdict, deque
from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime
import math


class VideoSummary(BaseModel):
    """视频摘要"""
    bvid: str
    title: str
    short_intro: str = ""
    key_points: List[str] = []
    target_audience: str = ""
    difficulty_level: str = "intermediate"  # beginner/intermediate/advanced
    tags: List[str] = []
    duration: Optional[int] = None  # 视频时长（秒）


class TopicCluster(BaseModel):
    """主题聚类"""
    cluster_id: int
    topic_name: str
    video_count: int = 0
    videos: List[VideoSummary] = []
    keywords: List[str] = []
    difficulty_distribution: Dict[str, int] = {}


class LearningStage(BaseModel):
    """学习阶段"""
    stage_id: int
    name: str
    description: str
    videos: List[VideoSummary] = []
    prerequisites: List[str] = []
    estimated_time: float = 0.0  # 小时


class LearningPath(BaseModel):
    """学习路径"""
    user_level: str = "beginner"  # beginner/intermediate/advanced
    total_videos: int = 0
    stages: List[LearningStage] = []
    estimated_hours: float = 0.0
    intro: str = ""


class LearningPathService:
    """学习路径推荐服务"""

    # 难度等级映射
    DIFFICULTY_LEVELS = {
        "beginner": 0,
        "intermediate": 1,
        "advanced": 2
    }

    # 主题优先级映射（基础主题优先）
    TOPIC_PRIORITY = {
        "入门": 1,
        "基础": 2,
        "初级": 2,
        "进阶": 3,
        "高级": 4,
        "实战": 4,
        "项目": 5
    }

    def __init__(self, llm=None):
        self.llm = llm

    async def generate_learning_path(
        self,
        clusters: List[TopicCluster],
        user_level: str = "beginner"
    ) -> LearningPath:
        """
        生成学习路径

        Args:
            clusters: 主题聚类列表
            user_level: 用户当前水平 beginner/intermediate/advanced

        Returns:
            LearningPath: 学习路径
        """
        if not clusters:
            return LearningPath(user_level=user_level, intro="暂无足够的学习内容")

        # 1. 构建视频依赖图
        graph = self._build_dependency_graph(clusters)

        # 2. 计算学习顺序（拓扑排序 + PageRank）
        learning_order = self._compute_learning_order(graph, clusters)

        # 3. 分阶段生成路径
        path = await self._generate_path_stages(
            learning_order,
            clusters,
            user_level
        )

        return path

    def _build_dependency_graph(
        self,
        clusters: List[TopicCluster]
    ) -> Dict[str, List[str]]:
        """
        构建依赖图

        边规则：
        1. 同一主题内： beginner -> intermediate -> advanced
        2. 跨主题：后验先修（如：数学 -> 物理）
        """
        graph = defaultdict(list)

        # 按主题内难度排序
        for cluster in clusters:
            videos = sorted(
                cluster.videos,
                key=lambda v: self.DIFFICULTY_LEVELS.get(
                    v.difficulty_level,
                    self.DIFFICULTY_LEVELS["intermediate"]
                )
            )

            # 添加难度递进边
            for i in range(len(videos) - 1):
                from_video = videos[i].bvid
                to_video = videos[i + 1].bvid
                graph[from_video].append(to_video)

        # 跨主题依赖（基于主题优先级）
        sorted_clusters = sorted(
            clusters,
            key=lambda c: self._get_topic_priority(c.topic_name)
        )

        for i in range(len(sorted_clusters) - 1):
            current_cluster = sorted_clusters[i]
            next_cluster = sorted_clusters[i + 1]

            # 连接两个主题的最后一节课到下一主题的第一节课
            if current_cluster.videos and next_cluster.videos:
                last_video = current_cluster.videos[-1]
                first_video = next_cluster.videos[0]
                graph[last_video.bvid].append(first_video.bvid)

        return dict(graph)

    def _compute_learning_order(
        self,
        graph: Dict[str, List[str]],
        clusters: List[TopicCluster]
    ) -> List[str]:
        """
        计算学习顺序

        使用改进的拓扑排序：
        1. 计算每个节点的入度
        2. 使用 PageRank 考虑节点重要性
        3. 结合两者生成顺序
        """
        # 获取所有视频
        all_videos = []
        for cluster in clusters:
            all_videos.extend([v.bvid for v in cluster.videos])

        # 计算入度
        in_degree = {v: 0 for v in all_videos}
        for from_v, to_vs in graph.items():
            for to_v in to_vs:
                if to_v in in_degree:
                    in_degree[to_v] += 1

        # 计算 PageRank
        pagerank = self._compute_pagerank(graph, all_videos)

        # 拓扑排序 + BFS + PageRank 优先级
        queue = deque([v for v in all_videos if in_degree[v] == 0])

        # 按 PageRank 分数排序初始队列
        queue = deque(sorted(queue, key=lambda x: pagerank.get(x, 0), reverse=True))

        result = []

        while queue:
            # 按主题优先级和 PageRank 排序
            queue = deque(sorted(
                queue,
                key=lambda x: (
                    self._get_topic_priority_by_bvid(x, clusters),
                    pagerank.get(x, 0)
                )
            ))

            current = queue.popleft()
            result.append(current)

            # 更新入度
            for next_v in graph.get(current, []):
                if next_v in in_degree:
                    in_degree[next_v] -= 1
                    if in_degree[next_v] == 0:
                        queue.append(next_v)

        # 处理未遍历到的节点（可能存在循环依赖）
        remaining = [v for v in all_videos if v not in result]
        result.extend(remaining)

        return result

    def _compute_pagerank(
        self,
        graph: Dict[str, List[str]],
        nodes: List[str],
        damping: float = 0.85,
        max_iterations: int = 100
    ) -> Dict[str, float]:
        """
        计算 PageRank

        Args:
            graph: 依赖图
            nodes: 所有节点
            damping: 阻尼系数
            max_iterations: 最大迭代次数

        Returns:
            PageRank 分数
        """
        n = len(nodes)
        if n == 0:
            return {}

        # 初始化
        pagerank = {node: 1.0 / n for node in nodes}

        # 构建反向图（入链）
        inlinks = defaultdict(list)
        for from_node, to_nodes in graph.items():
            for to_node in to_nodes:
                inlinks[to_node].append(from_node)

        # 迭代计算
        for _ in range(max_iterations):
            new_pagerank = {}

            for node in nodes:
                # 计算来自入链的贡献
                incoming = inlinks[node]
                if incoming:
                    rank_sum = sum(pagerank.get(in_node, 0) / len(graph.get(in_node, [node]))
                                  for in_node in incoming)
                    new_pagerank[node] = (1 - damping) / n + damping * rank_sum
                else:
                    # 没有入链的节点
                    new_pagerank[node] = (1 - damping) / n

            # 检查收敛
            diff = sum(abs(new_pagerank[node] - pagerank[node]) for node in nodes)
            pagerank = new_pagerank

            if diff < 1e-6:
                break

        return pagerank

    def _get_topic_priority(self, topic_name: str) -> int:
        """获取主题优先级（基础主题优先）"""
        for keyword, priority in self.TOPIC_PRIORITY.items():
            if keyword in topic_name:
                return priority
        return 2  # 默认优先级

    def _get_topic_priority_by_bvid(self, bvid: str, clusters: List[TopicCluster]) -> int:
        """通过 bvid 获取主题优先级"""
        for cluster in clusters:
            for video in cluster.videos:
                if video.bvid == bvid:
                    return self._get_topic_priority(cluster.topic_name)
        return 2

    async def _generate_path_stages(
        self,
        learning_order: List[str],
        clusters: List[TopicCluster],
        user_level: str
    ) -> LearningPath:
        """生成分阶段的学习路径"""

        # 构建视频映射
        video_map: Dict[str, VideoSummary] = {}
        for cluster in clusters:
            for video in cluster.videos:
                video_map[video.bvid] = video

        # 分阶段（每5个视频或难度变化时换阶段）
        stages: List[LearningStage] = []
        current_stage_videos: List[VideoSummary] = []
        current_difficulty = user_level  # 跟踪当前阶段的主要难度

        for bvid in learning_order:
            video = video_map.get(bvid)
            if not video:
                continue

            # 检查是否需要开启新阶段
            should_new_stage = (
                len(current_stage_videos) >= 5 or  # 达到5个视频
                (current_stage_videos and
                 self.DIFFICULTY_LEVELS.get(video.difficulty_level, 1) >
                 self.DIFFICULTY_LEVELS.get(current_difficulty, 1) + 1)  # 难度跳跃过大
            )

            if should_new_stage and current_stage_videos:
                # 保存当前阶段
                stage = self._create_stage(
                    stage_id=len(stages) + 1,
                    videos=current_stage_videos,
                    clusters=clusters
                )
                stages.append(stage)

                # 开始新阶段
                current_stage_videos = [video]
                current_difficulty = video.difficulty_level
            else:
                current_stage_videos.append(video)
                # 更新主要难度为出现最多的
                if len(current_stage_videos) > 1:
                    difficulty_counts = defaultdict(int)
                    for v in current_stage_videos:
                        difficulty_counts[v.difficulty_level] += 1
                    current_difficulty = max(
                        difficulty_counts,
                        key=difficulty_counts.get
                    )

        # 添加最后一个阶段
        if current_stage_videos:
            stage = self._create_stage(
                stage_id=len(stages) + 1,
                videos=current_stage_videos,
                clusters=clusters
            )
            stages.append(stage)

        # 生成整体路径介绍
        intro = await self._generate_path_intro(stages, user_level)

        # 计算预估学习时长
        estimated_hours = sum(stage.estimated_time for stage in stages)

        return LearningPath(
            user_level=user_level,
            total_videos=len(learning_order),
            stages=stages,
            estimated_hours=round(estimated_hours, 1),
            intro=intro
        )

    def _create_stage(
        self,
        stage_id: int,
        videos: List[VideoSummary],
        clusters: List[TopicCluster]
    ) -> LearningStage:
        """创建学习阶段"""
        # 获取阶段名称（基于主题）
        stage_name = self._generate_stage_name(videos, clusters)

        # 生成阶段描述
        description = self._generate_stage_description(videos)

        # 计算前置要求
        prerequisites = self._extract_prerequisites(videos)

        # 预估时长（假设每个视频平均10分钟）
        total_duration = sum(v.duration or 600 for v in videos)
        estimated_time = round(total_duration / 3600, 1)  # 转换为小时

        return LearningStage(
            stage_id=stage_id,
            name=stage_name,
            description=description,
            videos=videos,
            prerequisites=prerequisites,
            estimated_time=max(estimated_time, 0.5)  # 至少0.5小时
        )

    def _generate_stage_name(
        self,
        videos: List[VideoSummary],
        clusters: List[TopicCluster]
    ) -> str:
        """生成阶段名称"""
        if not videos:
            return "学习阶段"

        # 找到视频所属的主题
        video_topics = set()
        for video in videos:
            for cluster in clusters:
                if video in cluster.videos:
                    video_topics.add(cluster.topic_name)
                    break

        if video_topics:
            topics_str = "、".join(list(video_topics)[:2])
            return f"阶段{len(videos)}：{topics_str}"

        # 基于难度级别
        difficulty_counts = defaultdict(int)
        for v in videos:
            difficulty_counts[v.difficulty_level] += 1

        main_difficulty = max(difficulty_counts, key=difficulty_counts.get)
        difficulty_names = {
            "beginner": "入门",
            "intermediate": "进阶",
            "advanced": "高级"
        }

        return f"第{len(videos)}阶段：{difficulty_names.get(main_difficulty, '学习')}"

    def _generate_stage_description(self, videos: List[VideoSummary]) -> str:
        """生成阶段描述"""
        if not videos:
            return "本阶段暂无内容"

        # 收集关键要点
        all_key_points = []
        for video in videos[:3]:  # 只取前3个视频的要点
            all_key_points.extend(video.key_points[:2])

        if all_key_points:
            points_str = "；".join(all_key_points[:3])
            return f"本阶段将学习：{points_str}。共{len(videos)}个视频。"

        # 收集标签
        all_tags = set()
        for video in videos:
            all_tags.update(video.tags[:2])

        if all_tags:
            tags_str = "、".join(list(all_tags)[:5])
            return f"本阶段涵盖：{tags_str}。共{len(videos)}个视频。"

        return f"本阶段共{len(videos)}个视频，建议按顺序学习。"

    def _extract_prerequisites(self, videos: List[VideoSummary]) -> List[str]:
        """提取前置要求"""
        prerequisites = []

        # 查找需要前置知识的视频
        beginner_count = sum(1 for v in videos if v.difficulty_level == "beginner")
        advanced_count = sum(1 for v in videos if v.difficulty_level == "advanced")

        if advanced_count > 0 and beginner_count == 0:
            prerequisites.append("建议具备一定基础后再学习本阶段")

        # 基于标签推断
        all_tags = set()
        for video in videos:
            all_tags.update(video.tags)

        # 常见前置技能
        prereq_map = {
            "算法": "数据结构基础",
            "机器学习": "数学基础（线性代数、概率统计）",
            "深度学习": "机器学习基础",
            "React": "JavaScript 基础",
            "Vue": "JavaScript 基础",
            "Go": "编程基础",
            "Rust": "编程基础"
        }

        for tag, prereq in prereq_map.items():
            if tag in all_tags and prereq not in prerequisites:
                prerequisites.append(prereq)

        return prerequisites[:3]  # 最多3个

    async def _generate_path_intro(self, stages: List[LearningStage], user_level: str) -> str:
        """使用 LLM 生成整体路径介绍"""
        if not stages:
            return "暂无学习路径"

        # 如果有 LLM，使用 LLM 生成
        if self.llm:
            try:
                stage_info = []
                for i, stage in enumerate(stages[:3], 1):
                    topics = [v.title[:20] for v in stage.videos[:2]]
                    stage_info.append(f"第{i}阶段：{stage.name}，{len(stage.videos)}个视频")

                prompt = f"""你是一个学习规划专家。请为用户生成一个简洁的学习路径介绍。

用户当前水平：{user_level}
学习阶段：
{chr(10).join(stage_info)}

请生成一段50字以内的学习路径介绍，要体现循序渐进的特点。

要求：
1. 简洁有力，不超过50字
2. 体现从易到难的学习路径
3. 突出重点阶段
"""

                response = await self.llm.agenerate([prompt])
                intro = response.generations[0][0].text.strip()

                # 清理格式
                intro = intro.strip('"').strip("```").strip()

                return intro[:100]  # 限制长度
            except Exception:
                pass  # LLM 调用失败，使用默认介绍

        # 默认介绍
        level_names = {
            "beginner": "初学者",
            "intermediate": "有一定基础的",
            "advanced": "进阶学习者"
        }

        level_name = level_names.get(user_level, "学习者")

        if len(stages) == 1:
            return f"本学习路径为{level_name}设计，共{len(stages[0].videos)}个视频，建议按顺序学习。"

        return f"本学习路径为{level_name}设计，共{len(stages)}个阶段，{sum(len(s.videos) for s in stages)}个视频，循序渐进带你深入学习。"
