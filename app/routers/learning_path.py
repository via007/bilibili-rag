"""
Bilibili RAG 知识库系统

学习路径路由 - 推荐学习顺序
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/knowledge/path", tags=["知识库-学习路径"])


# ============== 响应模型 ==============

class PathVideoItem(BaseModel):
    """路径中的视频项"""
    bvid: str
    title: Optional[str] = None
    short_intro: Optional[str] = None
    difficulty_level: Optional[str] = None
    duration: Optional[int] = None


class LearningStageResponse(BaseModel):
    """学习阶段响应"""
    stage_id: int
    name: str
    description: str
    videos: List[PathVideoItem] = []
    prerequisites: List[str] = []
    estimated_time: float


class LearningPathResponse(BaseModel):
    """学习路径响应"""
    folder_id: int
    user_level: str
    total_videos: int
    estimated_hours: float
    intro: str
    stages: List[LearningStageResponse] = []
    generated_at: Optional[datetime] = None


# ============== 路由 ==============


@router.get("/{folder_id}", response_model=LearningPathResponse)
async def get_learning_path(
    folder_id: int,
    user_level: str = Query("beginner", description="用户水平: beginner/intermediate/advanced"),
    session_id: str = Query(..., description="用户登录 session"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取学习路径

    根据用户水平和收藏夹内容，生成推荐的学习顺序。
    """
    from app.services.learning_path import LearningPathService, TopicCluster, VideoSummary
    from app.services.clustering import TopicClusteringService
    from app.models import VideoCache, FavoriteFolder, FavoriteVideo

    # 验证收藏夹归属 - 使用传入的 session_id
    stmt = select(FavoriteFolder).where(
        FavoriteFolder.media_id == folder_id,
        FavoriteFolder.session_id == session_id
    )
    result = await db.execute(stmt)
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    # 获取该收藏夹的所有视频
    # 注意：FavoriteVideo.folder_id 关联的是 FavoriteFolder.id，不是 media_id
    actual_folder_id = folder.id
    stmt = select(FavoriteVideo).where(
        FavoriteVideo.folder_id == actual_folder_id,
        FavoriteVideo.is_selected == True
    )
    result = await db.execute(stmt)
    favorite_videos = result.scalars().all()

    if not favorite_videos:
        return LearningPathResponse(
            folder_id=folder_id,
            user_level=user_level,
            total_videos=0,
            estimated_hours=0,
            intro="暂无学习内容",
            stages=[]
        )

    # 获取视频内容
    bvids = [fv.bvid for fv in favorite_videos]
    stmt = select(VideoCache).where(VideoCache.bvid.in_(bvids))
    result = await db.execute(stmt)
    video_cache_list = result.scalars().all()

    video_cache_map = {v.bvid: v for v in video_cache_list}

    # 构建 VideoSummary 列表
    videos = []
    for fv in favorite_videos:
        vc = video_cache_map.get(fv.bvid)
        if vc:
            # 从 content 或 outline_json 获取摘要信息
            short_intro = ""
            key_points = []
            tags = []

            if vc.content:
                # 使用内容前200字作为简介
                short_intro = vc.content[:200] if len(vc.content) > 200 else vc.content

            if vc.outline_json:
                import json
                try:
                    outline = json.loads(vc.outline_json) if isinstance(vc.outline_json, str) else vc.outline_json
                    if isinstance(outline, list):
                        key_points = [item.get("title", "") for item in outline[:5]]
                except:
                    pass

            videos.append(VideoSummary(
                bvid=vc.bvid,
                title=vc.title or "",
                short_intro=short_intro,
                key_points=key_points,
                tags=tags,
                difficulty_level="intermediate",  # 默认
                duration=vc.duration
            ))

    if not videos:
        return LearningPathResponse(
            folder_id=folder_id,
            user_level=user_level,
            total_videos=0,
            estimated_hours=0,
            intro="暂无足够的学习内容",
            stages=[]
        )

    # 进行主题聚类
    clustering_service = TopicClusteringService()
    clusters = await clustering_service.cluster_videos(
        videos,
        n_clusters=min(5, len(videos) // 3 + 1) if len(videos) >= 5 else None,
        min_cluster_size=2
    )

    if not clusters:
        # 如果聚类失败，将所有视频作为一个主题
        clusters = [TopicCluster(
            cluster_id=1,
            topic_name="综合学习",
            video_count=len(videos),
            videos=videos,
            keywords=[],
            difficulty_distribution={"beginner": 0, "intermediate": len(videos), "advanced": 0}
        )]

    # 生成学习路径
    path_service = LearningPathService()
    learning_path = await path_service.generate_learning_path(
        clusters=clusters,
        user_level=user_level
    )

    # 转换为响应模型
    stages_response = [
        LearningStageResponse(
            stage_id=stage.stage_id,
            name=stage.name,
            description=stage.description,
            videos=[
                PathVideoItem(
                    bvid=v.bvid,
                    title=v.title,
                    short_intro=v.short_intro,
                    difficulty_level=v.difficulty_level,
                    duration=v.duration
                )
                for v in stage.videos
            ],
            prerequisites=stage.prerequisites,
            estimated_time=stage.estimated_time
        )
        for stage in learning_path.stages
    ]

    return LearningPathResponse(
        folder_id=folder_id,
        user_level=learning_path.user_level,
        total_videos=learning_path.total_videos,
        estimated_hours=learning_path.estimated_hours,
        intro=learning_path.intro,
        stages=stages_response,
        generated_at=datetime.utcnow()
    )


@router.post("/generate")
async def trigger_path_generation(
    folder_id: int,
    user_level: str = Query("beginner", description="用户水平: beginner/intermediate/advanced"),
    session_id: str = Query(..., description="用户登录 session"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发学习路径生成
    """
    from app.services.learning_path import LearningPathService, TopicCluster, VideoSummary
    from app.services.clustering import TopicClusteringService
    from app.models import VideoCache, FavoriteFolder, FavoriteVideo

    # 验证收藏夹归属 - 使用传入的 session_id
    stmt = select(FavoriteFolder).where(
        FavoriteFolder.media_id == folder_id,
        FavoriteFolder.session_id == session_id
    )
    result = await db.execute(stmt)
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    # TODO: 可以使用 background_tasks 异步处理
    # 这里直接返回消息，实际生成通过 GET 接口

    return {
        "message": "学习路径生成任务已提交",
        "folder_id": folder_id,
        "user_level": user_level,
        "tip": "请使用 GET /knowledge/path/{folder_id} 接口获取学习路径"
    }

