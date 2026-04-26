"""
Bilibili RAG 知识库系统

ASR 分P服务 - 仅做 ASR 转写，不涉及 RAG 向量存储
"""
import os
import time
from typing import Optional
from loguru import logger

from app.services.asr import ASRService
from app.services.bilibili import BilibiliService
from app.routers.asr import asr_tasks
from app.database import get_db_context
from app.models import VideoPage, VideoPageVersion


class ContentSource:
    """内容来源枚举"""
    ASR = "asr"
    USER_EDIT = "user_edit"


class ASRPageService:
    """
    分P ASR 处理服务

    职责：
    1. 获取单P视频音频（本地下载，不依赖过期URL）
    2. ASR 转写
    3. 写入 video_pages + video_page_versions

    不涉及：RAG 向量存储（那是独立流程）
    """

    def __init__(self):
        self.asr = ASRService()
        # bilibili_service 在运行时注入
        self.bili: Optional[BilibiliService] = None

    def set_bilibili_service(self, bili: BilibiliService):
        """设置 B站 服务（运行时注入）"""
        self.bili = bili

    async def process_page(
        self,
        task_id: str,
        bvid: str,
        cid: int,
        page_index: int,
        page_title: str,
    ):
        """
        后台 ASR 处理流程（仅此而已）：
        1. 更新任务状态 = processing
        2. 获取音频 URL 并下载到本地
        3. ASR 转写（本地文件上传，避免 URL 过期 403）
        4. 写入 video_pages.content
        5. 写入 video_page_versions（新版本）
        6. 更新任务状态 = done
        7. 清理临时文件

        不涉及 RAG 向量存储（那是独立流程）
        """
        tmp_file = None
        try:
            # 更新任务状态
            asr_tasks[task_id]["status"] = "processing"
            asr_tasks[task_id]["progress"] = 10
            asr_tasks[task_id]["message"] = "获取音频..."

            # 获取音频 URL
            if not self.bili:
                self.bili = BilibiliService()

            audio_url = await self.bili.get_audio_url(bvid, cid)
            if not audio_url:
                raise Exception(f"无法获取音频 URL: bvid={bvid}, cid={cid}")

            asr_tasks[task_id]["progress"] = 25
            asr_tasks[task_id]["message"] = "Downloading audio..."
            # 下载到本地（避免 URL 过期导致 403）
            tmp_dir = os.path.join("data", "asr_tmp")
            os.makedirs(tmp_dir, exist_ok=True)

            tmp_file = os.path.join(tmp_dir, f"{bvid}_{cid}_{int(time.time())}.m4s")
            ok = await self.bili.download_audio_to_file(audio_url, tmp_file)
            if not ok or not os.path.exists(tmp_file):
                raise Exception(f"音频下载失败: bvid={bvid}, cid={cid}")

            file_size = os.path.getsize(tmp_file)
            if file_size < 1024:
                raise Exception(f"音频文件过小({file_size} bytes): bvid={bvid}, cid={cid}")

            asr_tasks[task_id]["progress"] = 55
            asr_tasks[task_id]["message"] = "Running ASR..."

            # ASR 转写（本地文件上传，避免 URL 过期 403）
            text = await self.asr.transcribe_local_file(tmp_file)
            if not text or len(text) < 50:
                raise Exception(f"ASR 内容过少: {len(text) if text else 0} 字符")

            asr_tasks[task_id]["progress"] = 85
            asr_tasks[task_id]["message"] = "Writing database..."

            # 写入数据库
            async with get_db_context() as db:
                # 查询当前 page 记录
                from sqlalchemy import select
                result = await db.execute(
                    select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                )
                page = result.scalar_one_or_none()

                if page:
                    # 写入 video_pages
                    page.content = text
                    page.content_source = "asr"
                    page.is_processed = True

                    # 写入 video_page_versions（新版本）
                    version_record = VideoPageVersion(
                        bvid=bvid,
                        cid=cid,
                        page_index=page_index,
                        version=page.version,
                        content=text,
                        content_source="asr",
                        is_latest=True,
                    )
                    db.add(version_record)

                    # 旧版本 is_latest = false
                    old_result = await db.execute(
                        select(VideoPageVersion)
                        .where(
                            VideoPageVersion.bvid == bvid,
                            VideoPageVersion.cid == cid,
                            VideoPageVersion.version < page.version
                        )
                    )
                    old_versions = old_result.scalars().all()
                    for old_v in old_versions:
                        old_v.is_latest = False

                    await db.commit()

            # 完成
            asr_tasks[task_id]["status"] = "done"
            asr_tasks[task_id]["progress"] = 100
            asr_tasks[task_id]["message"] = "ASR 完成"
            logger.info(f"[ASR] 完成 bvid={bvid}, cid={cid}, 长度={len(text)}")

        except Exception as e:
            logger.error(f"[ASR] 失败 bvid={bvid}, cid={cid}: {e}")
            asr_tasks[task_id]["status"] = "failed"
            asr_tasks[task_id]["message"] = f"ASR 失败: {str(e)}"

            # 尝试更新数据库状态
            try:
                async with get_db_context() as db:
                    from sqlalchemy import select
                    result = await db.execute(
                        select(VideoPage).where(VideoPage.bvid == bvid, VideoPage.cid == cid)
                    )
                    page = result.scalar_one_or_none()
                    if page:
                        page.is_processed = True  # 标记为已处理（即使失败）
                        await db.commit()
            except Exception as db_err:
                logger.error(f"[ASR] 更新数据库失败: {db_err}")

        finally:
            # 清理临时文件
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                    logger.debug(f"[ASR] 清理临时文件: {tmp_file}")
                except Exception as e:
                    logger.warning(f"[ASR] 清理临时文件失败: {e}")
