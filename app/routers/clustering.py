"""
Bilibili RAG 知识库系统

主题聚类路由 - 收藏夹视频主题聚类
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional, Dict
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_session

router = APIRouter(prefix="/knowledge/clusters", tags=["知识库-主题聚类"])


# ============== 响应模型 ==============

class ClusterVideoItem(BaseModel):
    """聚类中的视频项"""
    bvid: str
    title: Optional[str] = None
    short_intro: Optional[str] = None
    difficulty_level: Optional[str] = None


class TopicClusterResponse(BaseModel):
    """主题聚类响应"""
    cluster_id: int
    topic_name: Optional[str] = None
    keywords: Optional[List[str]] = None
    video_count: int = 0
    difficulty_distribution: Optional[Dict[str, int]] = None
    videos: List[ClusterVideoItem] = []


class ClustersResponse(BaseModel):
    """聚类列表响应"""
    folder_id: int
    clusters: List[TopicClusterResponse]
    generated_at: Optional[datetime] = None


class ClusterGenerateRequest(BaseModel):
    """手动生成聚类请求"""
    folder_id: int
    n_clusters: Optional[int] = None


class ClusterGenerateResponse(BaseModel):
    """生成聚类响应"""
    folder_id: int
    message: str
    task_id: Optional[str] = None


# ============== 辅助函数 ==============

async def get_clusters_from_db(db: AsyncSession, folder_id: int) -> Optional[dict]:
    """从数据库获取聚类结果"""
    try:
        from app.models import TopicCluster, ClusterVideo, VideoCache, VideoSummaryDB

        # 获取聚类
        result = await db.execute(
            select(TopicCluster)
            .where(TopicCluster.folder_id == folder_id)
            .order_by(TopicCluster.cluster_index)
        )
        clusters = result.scalars().all()

        if not clusters:
            return None

        clusters_data = []
        for cluster in clusters:
            # 获取聚类中的视频
            video_result = await db.execute(
                select(ClusterVideo.bvid)
                .where(ClusterVideo.cluster_id == cluster.id)
                .order_by(ClusterVideo.order_index)
            )
            bvids = [row[0] for row in video_result.fetchall()]

            # 获取视频详情
            videos = []
            for bvid in bvids:
                # 尝试从 VideoCache 获取标题
                cache_result = await db.execute(
                    select(VideoCache.title, VideoCache.pic_url)
                    .where(VideoCache.bvid == bvid)
                )
                cache_row = cache_result.first()
                title = cache_row[0] if cache_row else bvid

                # 尝试获取摘要
                summary_result = await db.execute(
                    select(VideoSummaryDB.short_intro, VideoSummaryDB.difficulty_level)
                    .where(VideoSummaryDB.bvid == bvid)
                )
                summary_row = summary_result.first()
                short_intro = summary_row[0] if summary_row else None
                difficulty_level = summary_row[1] if summary_row else None

                videos.append(ClusterVideoItem(
                    bvid=bvid,
                    title=title,
                    short_intro=short_intro,
                    difficulty_level=difficulty_level,
                ))

            # 统计难度分布
            difficulty_dist: Dict[str, int] = {"beginner": 0, "intermediate": 0, "advanced": 0}
            for v in videos:
                if v.difficulty_level in difficulty_dist:
                    difficulty_dist[v.difficulty_level] += 1

            clusters_data.append(TopicClusterResponse(
                cluster_id=cluster.cluster_index,
                topic_name=cluster.topic_name,
                keywords=cluster.keywords,
                video_count=cluster.video_count,
                difficulty_distribution=difficulty_dist,
                videos=videos,
            ))

        return {
            "folder_id": folder_id,
            "clusters": clusters_data,
            "generated_at": clusters[0].generated_at if clusters else None,
        }

    except Exception as e:
        logger.error(f"获取聚类结果失败: {e}")
        return None


async def generate_clusters_task(folder_id: int, n_clusters: Optional[int] = None):
    """后台生成聚类任务"""
    try:
        from app.services.clustering import TopicClusteringService
        from app.services.llm_factory import get_llm_client as get_llm
        from app.database import get_db_context

        llm = get_llm()
        clustering_service = TopicClusteringService(llm)

        async with get_db_context() as db:
            # 获取收藏夹中的所有视频
            from app.models import FavoriteVideo, FavoriteFolder, VideoCache, VideoSummaryDB

            # 获取收藏夹（使用 media_id 查询）
            folder_result = await db.execute(
                select(FavoriteFolder).where(FavoriteFolder.media_id == folder_id)
            )
            folder = folder_result.scalar_one_or_none()
            if not folder:
                logger.warning(f"收藏夹 {folder_id} 不存在")
                return

            # 获取视频列表（使用 FavoriteFolder.id 关联，只统计已选中的视频）
            video_result = await db.execute(
                select(FavoriteVideo.bvid)
                .where(FavoriteVideo.folder_id == folder.id)
                .where(FavoriteVideo.is_selected == True)
            )
            bvids = [row[0] for row in video_result.fetchall()]

            logger.info(f"收藏夹 {folder_id} 已有 {len(bvids)} 个已选中的视频进行聚类")

            if len(bvids) < 2:
                logger.warning(f"收藏夹 {folder_id} 已选中的视频太少（{len(bvids)}个），无法聚类，至少需要2个")
                return

            # 获取视频摘要列表
            videos_data = []
            for bvid in bvids:
                cache_result = await db.execute(
                    select(VideoCache).where(VideoCache.bvid == bvid)
                )
                cache = cache_result.scalar_one_or_none()
                if not cache or not cache.content:
                    continue

                # 获取摘要
                summary_result = await db.execute(
                    select(VideoSummaryDB).where(VideoSummaryDB.bvid == bvid)
                )
                summary = summary_result.scalar_one_or_none()

                videos_data.append({
                    "bvid": bvid,
                    "title": cache.title,
                    "content": cache.content[:5000],  # 截取内容用于聚类
                    "short_intro": summary.short_intro if summary else cache.title,
                    "difficulty_level": summary.difficulty_level if summary else "intermediate",
                })

            if len(videos_data) < 2:
                logger.warning(f"收藏夹 {folder_id} 有效视频太少，无法聚类")
                return

            # 执行聚类
            clusters = await clustering_service.cluster_videos(videos_data, n_clusters)

            # 保存聚类结果
            from app.models import TopicCluster, ClusterVideo

            # 删除旧聚类
            await db.execute(
                select(TopicCluster).where(TopicCluster.folder_id == folder_id)
            )
            old_clusters = await db.execute(
                select(TopicCluster.id).where(TopicCluster.folder_id == folder_id)
            )
            old_ids = [row[0] for row in old_clusters.fetchall()]
            if old_ids:
                for old_id in old_ids:
                    await db.execute(
                        select(ClusterVideo).where(ClusterVideo.cluster_id == old_id)
                    )
                await db.execute(
                    delete(ClusterVideo).where(ClusterVideo.cluster_id.in_(old_ids))
                )
                await db.execute(
                    delete(TopicCluster).where(TopicCluster.folder_id == folder_id)
                )

            # 保存新聚类
            for cluster in clusters:
                topic_cluster = TopicCluster(
                    folder_id=folder_id,
                    cluster_index=cluster.get("cluster_id", 0),
                    topic_name=cluster.get("topic_name"),
                    keywords=cluster.get("keywords"),
                    video_count=len(cluster.get("videos", [])),
                    difficulty_distribution=cluster.get("difficulty_distribution"),
                    generated_at=datetime.utcnow(),
                )
                db.add(topic_cluster)
                await db.flush()

                # 保存视频关联
                for idx, video in enumerate(cluster.get("videos", [])):
                    cluster_video = ClusterVideo(
                        cluster_id=topic_cluster.id,
                        bvid=video.get("bvid"),
                        order_index=idx,
                    )
                    db.add(cluster_video)

            await db.commit()
            logger.info(f"收藏夹 {folder_id} 聚类生成完成，共 {len(clusters)} 个聚类")

    except Exception as e:
        logger.error(f"生成聚类失败 [{folder_id}]: {e}")


# ============== API 路由 ==============

# 注意：具体路径必须在参数化路径之前
@router.post("/generate", response_model=ClusterGenerateResponse)
async def generate_clusters(
    request: ClusterGenerateRequest,
    background_tasks: BackgroundTasks,
):
    """手动生成主题聚类"""
    folder_id = request.folder_id

    # 检查服务是否可用
    try:
        from app.services.llm_factory import get_llm_client as get_llm
        llm = get_llm()
    except Exception as e:
        logger.error(f"LLM 服务不可用: {e}")
        raise HTTPException(status_code=503, detail="LLM 服务暂不可用")

    # 使用后台任务处理
    background_tasks.add_task(generate_clusters_task, folder_id, request.n_clusters)

    return ClusterGenerateResponse(
        folder_id=folder_id,
        message="聚类生成任务已提交，请在稍后查询结果",
    )


@router.get("/{folder_id}", response_model=ClustersResponse)
async def get_clusters(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取收藏夹的主题聚类"""
    clusters_data = await get_clusters_from_db(db, folder_id)

    if not clusters_data:
        raise HTTPException(
            status_code=404,
            detail=f"收藏夹 {folder_id} 暂无聚类结果，请先生成聚类"
        )

    return ClustersResponse(
        folder_id=folder_id,
        clusters=clusters_data["clusters"],
        generated_at=clusters_data.get("generated_at"),
    )
