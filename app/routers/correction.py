"""
Bilibili RAG 知识库系统
人工校正管理路由
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from loguru import logger
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database import get_db
from app.models import (
    VideoCache,
    CorrectionHistory,
    FavoriteFolder,
    FavoriteVideo,
    UserSession,
    CorrectionListResponse,
    CorrectionVideo,
    CorrectionDetail,
    CorrectionSubmitRequest,
    CorrectionSubmitResponse,
    Sentence,
    QualityReport,
    CorrectionHistoryResponse,
    CorrectionHistoryItem,
)
from app.services.asr_quality import get_asr_quality_service

router = APIRouter(prefix="/correction", tags=["校正管理"])


async def verify_user_owns_video(db: AsyncSession, user_session_id: str, bvid: str) -> bool:
    """
    验证用户是否拥有该视频（用户收藏夹中包含该视频）

    Args:
        db: 数据库会话
        user_session_id: 用户会话 ID
        bvid: 视频 BV 号

    Returns:
        bool: 用户是否拥有该视频
    """
    try:
        # 1. 获取用户的 bili_mid
        session_stmt = select(UserSession.bili_mid).where(
            UserSession.session_id == user_session_id,
            UserSession.is_valid == True
        )
        session_result = await db.execute(session_stmt)
        bili_mid = session_result.scalar()

        if not bili_mid:
            return False

        # 2. 查找该用户的所有 session_id
        sessions_stmt = select(UserSession.session_id).where(
            UserSession.bili_mid == bili_mid
        )
        sessions_result = await db.execute(sessions_stmt)
        user_sessions = [row[0] for row in sessions_result.fetchall()]

        if not user_sessions:
            return False

        # 3. 检查视频是否在用户的收藏夹中
        folder_stmt = select(FavoriteFolder.id).where(
            FavoriteFolder.session_id.in_(user_sessions)
        )
        folder_result = await db.execute(folder_stmt)
        folder_ids = [row[0] for row in folder_result.fetchall()]

        if not folder_ids:
            return False

        # 4. 检查视频是否在收藏夹中
        video_stmt = select(FavoriteVideo).where(
            FavoriteVideo.folder_id.in_(folder_ids),
            FavoriteVideo.bvid == bvid
        ).limit(1)
        video_result = await db.execute(video_stmt)
        video = video_result.scalar_one_or_none()

        return video is not None
    except Exception as e:
        logger.warning(f"验证用户视频所有权失败: {e}")
        return False


async def verify_user_has_any_video(db: AsyncSession, user_session_id: str) -> bool:
    """
    验证用户是否有任何视频

    Args:
        db: 数据库会话
        user_session_id: 用户会话 ID

    Returns:
        bool: 用户是否有视频
    """
    try:
        # 1. 获取用户的 bili_mid
        session_stmt = select(UserSession.bili_mid).where(
            UserSession.session_id == user_session_id,
            UserSession.is_valid == True
        )
        session_result = await db.execute(session_stmt)
        bili_mid = session_result.scalar()

        if not bili_mid:
            return False

        # 2. 查找该用户的所有 session_id
        sessions_stmt = select(UserSession.session_id).where(
            UserSession.bili_mid == bili_mid
        )
        sessions_result = await db.execute(sessions_stmt)
        user_sessions = [row[0] for row in sessions_result.fetchall()]

        if not user_sessions:
            return False

        # 3. 检查是否有收藏夹
        folder_stmt = select(FavoriteFolder.id).where(
            FavoriteFolder.session_id.in_(user_sessions)
        )
        folder_result = await db.execute(folder_stmt)
        folder_ids = [row[0] for row in folder_result.fetchall()]

        return len(folder_ids) > 0
    except Exception as e:
        logger.warning(f"验证用户视频存在失败: {e}")
        return False


async def get_user_folder_ids(db: AsyncSession, user_session_id: str) -> list[int]:
    """获取用户收藏夹 ID 列表"""
    try:
        # 1. 获取用户的 bili_mid
        session_stmt = select(UserSession.bili_mid).where(
            UserSession.session_id == user_session_id,
            UserSession.is_valid == True
        )
        session_result = await db.execute(session_stmt)
        bili_mid = session_result.scalar()

        if not bili_mid:
            return []

        # 2. 查找该用户的所有 session_id
        sessions_stmt = select(UserSession.session_id).where(
            UserSession.bili_mid == bili_mid
        )
        sessions_result = await db.execute(sessions_stmt)
        user_sessions = [row[0] for row in sessions_result.fetchall()]

        if not user_sessions:
            return []

        # 3. 获取收藏夹 ID
        folder_stmt = select(FavoriteFolder.id).where(
            FavoriteFolder.session_id.in_(user_sessions)
        )
        folder_result = await db.execute(folder_stmt)
        return [row[0] for row in folder_result.fetchall()]
    except Exception as e:
        logger.warning(f"获取用户收藏夹失败: {e}")
        return []


async def get_user_bvids(db: AsyncSession, user_session_id: str) -> set:
    """获取用户收藏的所有视频 BV 号"""
    folder_ids = await get_user_folder_ids(db, user_session_id)
    if not folder_ids:
        return set()

    stmt = select(FavoriteVideo.bvid).where(
        FavoriteVideo.folder_id.in_(folder_ids)
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.fetchall()}


@router.get("/list", response_model=CorrectionListResponse)
async def list_corrections(
    user_session_id: str = Query(..., description="用户登录 session"),
    min_quality: float = Query(0.7, ge=0, le=1, description="最大质量分（高于此不显示）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    include_corrected: bool = Query(False, description="是否包含已校正的"),
    db: AsyncSession = Depends(get_db)
):
    """获取待校正列表"""
    # 验证用户是否有视频
    has_videos = await verify_user_has_any_video(db, user_session_id)
    if not has_videos:
        return CorrectionListResponse(videos=[], total=0, page=page, page_size=page_size)

    # 获取用户收藏的视频 BV 号
    user_bvids = await get_user_bvids(db, user_session_id)
    if not user_bvids:
        return CorrectionListResponse(videos=[], total=0, page=page, page_size=page_size)

    # 构建查询条件，只查询用户收藏的视频
    conditions = [
        VideoCache.bvid.in_(user_bvids),
        VideoCache.is_corrected == include_corrected,
        VideoCache.asr_quality_score != None,
    ]

    if not include_corrected:
        conditions.append(VideoCache.asr_quality_score < min_quality)

    # 查询总数
    count_stmt = select(func.count()).select_from(VideoCache).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 查询列表
    offset = (page - 1) * page_size
    stmt = (
        select(VideoCache)
        .where(*conditions)
        .order_by(desc(VideoCache.asr_quality_score), desc(VideoCache.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    videos = result.scalars().all()

    video_list = []
    for video in videos:
        content_preview = ""
        if video.content:
            content_preview = video.content[:100] + "..." if len(video.content) > 100 else video.content

        video_list.append(CorrectionVideo(
            bvid=video.bvid,
            title=video.title,
            asr_quality_score=video.asr_quality_score,
            asr_quality_flags=video.asr_quality_flags,
            content_preview=content_preview,
            is_corrected=video.is_corrected,
            created_at=video.created_at
        ))

    return CorrectionListResponse(
        videos=video_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{bvid}", response_model=CorrectionDetail)
async def get_correction(
    bvid: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    db: AsyncSession = Depends(get_db)
):
    """获取校正页面内容"""
    # 验证用户是否拥有该视频
    is_owner = await verify_user_owns_video(db, user_session_id, bvid)
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权限访问该视频")

    stmt = select(VideoCache).where(VideoCache.bvid == bvid)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    # 如果有校正内容，使用校正内容；否则使用原始内容
    content = video.corrected_content or video.content or ""

    # 生成句子列表（从内容中简单拆分）
    sentences = []
    if content:
        # 简单的句子拆分（按句号、问号、感叹号）
        import re
        sentence_texts = re.split(r'([。！？\n])', content)
        sentence_texts = [s for s in sentence_texts if s.strip()]

        current_id = 1
        current_text = ""
        current_start = 0.0
        for i, part in enumerate(sentence_texts):
            if part in '。！？\n':
                # 结束当前句子
                if current_text:
                    # 确定是否有标记
                    is_flagged = False
                    confidence = 0.8  # 默认置信度

                    # 如果有质量标记，检查是否应该标记
                    if video.asr_quality_flags:
                        if "low_confidence" in video.asr_quality_flags:
                            is_flagged = True
                            confidence = video.asr_quality_score or 0.5

                    sentences.append(Sentence(
                        id=current_id,
                        text=current_text + part,
                        start=current_start,
                        end=current_start + 5.0,  # 估算时长
                        confidence=confidence,
                        is_flagged=is_flagged
                    ))
                    current_id += 1
                    current_start += 5.0
                current_text = ""
            else:
                current_text += part

        # 处理最后一个句子
        if current_text:
            sentences.append(Sentence(
                id=current_id,
                text=current_text,
                start=current_start,
                end=current_start + 5.0,
                confidence=video.asr_quality_score or 0.8,
                is_flagged=False
            ))

    # 生成质量报告
    quality_report = None
    if video.asr_quality_score is not None:
        quality_service = get_asr_quality_service()
        # 创建模拟的 ASR 结果用于评估
        from app.services.asr_local import ASRResult, Sentence as ASRSentence

        asr_sentences = [ASRSentence(
            text=s.text,
            start=s.start,
            end=s.end,
            confidence=s.confidence
        ) for s in sentences]

        asr_result = ASRResult(
            text=content,
            sentences=asr_sentences,
            confidence_avg=video.asr_quality_score,
            confidence_min=video.asr_quality_score * 0.8,
            duration=video.asr_duration or 0,
            word_count=len(content)
        )

        quality_report_obj = await quality_service.evaluate(asr_result, video.asr_duration)
        quality_report = QualityReport(
            quality_score=quality_report_obj.quality_score,
            quality_grade=quality_report_obj.quality_grade,
            flags=quality_report_obj.flags,
            confidence_avg=quality_report_obj.confidence_avg,
            confidence_min=quality_report_obj.confidence_min,
            audio_quality=quality_report_obj.audio_quality,
            speech_ratio=quality_report_obj.speech_ratio,
            suggestions=quality_report_obj.suggestions
        )

    return CorrectionDetail(
        bvid=video.bvid,
        title=video.title,
        content=content,
        sentences=sentences,
        quality_report=quality_report
    )


@router.post("/{bvid}", response_model=CorrectionSubmitResponse)
async def submit_correction(
    bvid: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    request: CorrectionSubmitRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """提交校正"""
    # 验证用户是否拥有该视频
    is_owner = await verify_user_owns_video(db, user_session_id, bvid)
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权限修改该视频")

    stmt = select(VideoCache).where(VideoCache.bvid == bvid)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    # 保存原始内容用于历史记录
    original_content = video.content or ""

    # 更新视频的校正内容
    video.corrected_content = request.content
    video.is_corrected = True
    video.corrected_at = datetime.utcnow()
    video.corrected_by = "user"

    # 记录校正历史
    char_diff = abs(len(request.content) - len(original_content))
    word_diff = abs(len(request.content.split()) - len(original_content.split()))

    history = CorrectionHistory(
        bvid=bvid,
        original_content=original_content,
        corrected_content=request.content,
        char_diff=char_diff,
        word_diff=word_diff,
        correction_type="manual"
    )
    db.add(history)

    await db.commit()
    await db.refresh(video)

    return CorrectionSubmitResponse(
        success=True,
        message="校正已保存",
        is_corrected=video.is_corrected
    )


@router.get("/{bvid}/history", response_model=CorrectionHistoryResponse)
async def get_correction_history(
    bvid: str,
    user_session_id: str = Query(..., description="用户登录 session"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取校正历史"""
    # 验证用户是否拥有该视频
    is_owner = await verify_user_owns_video(db, user_session_id, bvid)
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权限访问该视频")

    # 查询总数
    count_stmt = select(func.count()).select_from(CorrectionHistory).where(
        CorrectionHistory.bvid == bvid
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 查询列表
    offset = (page - 1) * page_size
    stmt = (
        select(CorrectionHistory)
        .where(CorrectionHistory.bvid == bvid)
        .order_by(desc(CorrectionHistory.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    history_items = result.scalars().all()

    history_list = [
        CorrectionHistoryItem(
            id=item.id,
            original_content=item.original_content,
            corrected_content=item.corrected_content,
            char_diff=item.char_diff,
            word_diff=item.word_diff,
            correction_type=item.correction_type,
            created_at=item.created_at
        )
        for item in history_items
    ]

    return CorrectionHistoryResponse(
        history=history_list,
        total=total,
        page=page,
        page_size=page_size
    )
