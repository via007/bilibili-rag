"""
Bilibili RAG 知识库系统

视频内容获取服务 - 二级降级策略
"""
from typing import Optional
from loguru import logger
from app.models import VideoContent, ContentSource
from app.services.bilibili import BilibiliService
from app.services.asr import ASRService


class ContentFetcher:
    """
    视频内容获取器
    
    采用二级降级策略：
    1. 音频转写（ASR）
    2. 视频基本信息 (兜底)
    """
    
    def __init__(self, bilibili_service: BilibiliService, asr_service: ASRService):
        self.bili = bilibili_service
        self.asr = asr_service
    
    async def fetch_content(self, bvid: str, cid: int = None, title: str = None) -> VideoContent:
        """
        获取视频内容，自动降级
        
        Args:
            bvid: 视频 BV 号
            cid: 视频 cid (如果没有会自动获取)
            title: 视频标题 (如果没有会自动获取)
            
        Returns:
            VideoContent 对象
        """
        # 获取视频基本信息
        video_info = None
        if not cid or not title:
            try:
                video_info = await self.bili.get_video_info(bvid)
                if not cid:
                    cid = video_info.get("cid")
                if not title:
                    title = video_info.get("title", "未知标题")
            except Exception as e:
                logger.error(f"获取视频信息失败 [{bvid}]: {e}")
                return VideoContent(
                    bvid=bvid,
                    title=title or "未知标题",
                    content="无法获取视频信息",
                    source=ContentSource.BASIC_INFO
                )
        
        description = video_info.get("desc", "") if video_info else ""
        
        # Level 1: 跳过 AI 摘要，优先使用 ASR
        logger.info(f"[{bvid}] 已跳过 AI 摘要，优先使用 ASR")

        asr_text = await self._try_asr(bvid, cid)
        if asr_text:
            logger.info(f"[{bvid}] 使用 ASR 文本")
            return VideoContent(
                bvid=bvid,
                title=title,
                content=asr_text,
                source=ContentSource.ASR
            )
        
        # ASR 失败时，补齐基础信息（避免遗漏简介）
        if not video_info:
            try:
                video_info = await self.bili.get_video_info(bvid)
            except Exception as e:
                logger.debug(f"[{bvid}] 获取视频信息失败(兜底): {e}")

        if video_info and not description:
            description = video_info.get("desc", "") or description

        # Level 3: 使用基本信息兜底
        logger.info(f"[{bvid}] 使用基本信息")
        basic_content = f"视频标题：{title}"
        if description:
            basic_content += f"\n\n视频简介：{description}"
        
        return VideoContent(
            bvid=bvid,
            title=title,
            content=basic_content,
            source=ContentSource.BASIC_INFO
        )

    async def _try_asr(self, bvid: str, cid: int) -> Optional[str]:
        """尝试进行音频转写"""
        try:
            audio_url = await self.bili.get_audio_url(bvid, cid)
            if not audio_url:
                logger.info(f"[{bvid}] 未获取到音频 URL")
                return None
            text = await self.asr.transcribe_url(audio_url)
            if not text or len(text) < 50:
                logger.info(f"[{bvid}] ASR 内容过少")
                return None
            preview = text[:120].replace("\n", " ").strip()
            logger.info(f"[{bvid}] ASR 成功，长度={len(text)}，预览：{preview}")
            return text
        except Exception as e:
            logger.warning(f"[{bvid}] ASR 失败: {e}")
            return None

    async def _try_ai_summary(
        self, 
        bvid: str, 
        cid: int, 
        up_mid: int = None
    ) -> Optional[dict]:
        """尝试获取 AI 摘要"""
        try:
            result = await self.bili.get_video_summary(bvid, cid, up_mid)
            
            if not result:
                return None
            
            # 检查是否有有效摘要
            inner_code = result.get("code", -1)
            if inner_code != 0:
                logger.debug(f"[{bvid}] AI 摘要不可用: code={inner_code}")
                return None
            
            model_result = result.get("model_result", {})
            summary = model_result.get("summary", "")
            
            if not summary:
                logger.debug(f"[{bvid}] AI 摘要为空")
                return None
            
            # 解析分段提纲
            outline = []
            for item in model_result.get("outline", []):
                outline_item = {
                    "title": item.get("title", ""),
                    "timestamp": item.get("timestamp", 0),
                    "points": []
                }
                for point in item.get("part_outline", []):
                    outline_item["points"].append({
                        "content": point.get("content", ""),
                        "timestamp": point.get("timestamp", 0)
                    })
                outline.append(outline_item)
            
            return {
                "summary": summary,
                "outline": outline
            }
            
        except Exception as e:
            logger.warning(f"[{bvid}] 获取 AI 摘要失败: {e}")
            return None
    
    async def _try_subtitle(self, bvid: str, cid: int, video_info: Optional[dict] = None) -> Optional[str]:
        """尝试获取字幕"""
        try:
            def pick_subtitle(subtitles: list) -> Optional[dict]:
                """优先选中文且人工字幕，没有就回退到中文自动字幕"""
                if not subtitles:
                    return None
                def is_zh(sub):
                    lan = sub.get("lan", "") or ""
                    return "zh" in lan.lower() or "cn" in lan.lower()
                for sub in subtitles:
                    if is_zh(sub) and str(sub.get("ai_status", "0")) == "0":
                        return sub
                for sub in subtitles:
                    if is_zh(sub):
                        return sub
                return subtitles[0]

            def extract_subtitles(data: dict) -> list:
                subtitle_block = (data or {}).get("subtitle", {}) or {}
                return subtitle_block.get("subtitles") or subtitle_block.get("list") or []

            def extract_url(sub: dict) -> str:
                return sub.get("subtitle_url") or sub.get("url") or ""

            cookies = self.bili._get_cookies()
            has_login = bool(cookies.get("SESSDATA"))

            # 第一次尝试：播放器接口
            aid = video_info.get("aid") if video_info else None
            player_info = await self.bili.get_player_info(bvid, cid, aid=aid)

            subtitles = extract_subtitles(player_info or {})
            if subtitles:
                selected_subtitle = pick_subtitle(subtitles)
                subtitle_url = extract_url(selected_subtitle or {})
                if subtitle_url:
                    subtitle_text = await self.bili.download_subtitle(subtitle_url)
                    if subtitle_text and len(subtitle_text) >= 50:
                        preview = subtitle_text[:120].replace("\n", " ").strip()
                        logger.info(f"[{bvid}] 字幕获取成功，长度={len(subtitle_text)}，预览：{preview}")
                        return subtitle_text
                    logger.info(f"[{bvid}] 字幕内容过少，已忽略")
                else:
                    logger.info(f"[{bvid}] 字幕地址为空，无法下载")
            else:
                logger.info(f"[{bvid}] 播放器字幕为空（登录态={'已设置' if has_login else '未设置'}）")

            # 如果没有 video_info，尝试获取以补齐 aid 与字幕列表
            if not video_info:
                try:
                    video_info = await self.bili.get_video_info(bvid)
                except Exception as e:
                    logger.debug(f"[{bvid}] 获取视频信息失败(字幕兜底): {e}")
                    video_info = None

            # 第二次尝试：带 aid 再取一次播放器字幕
            if video_info and not aid:
                aid = video_info.get("aid")
                if aid:
                    player_info = await self.bili.get_player_info(bvid, cid, aid=aid)
                    subtitles = extract_subtitles(player_info or {})
                    if subtitles:
                        selected_subtitle = pick_subtitle(subtitles)
                        subtitle_url = extract_url(selected_subtitle or {})
                        if subtitle_url:
                            subtitle_text = await self.bili.download_subtitle(subtitle_url)
                            if subtitle_text and len(subtitle_text) >= 50:
                                preview = subtitle_text[:120].replace("\n", " ").strip()
                                logger.info(f"[{bvid}] 字幕获取成功(补aid)，长度={len(subtitle_text)}，预览：{preview}")
                                return subtitle_text
                            logger.info(f"[{bvid}] 字幕内容过少，已忽略")
                        else:
                            logger.info(f"[{bvid}] 字幕地址为空，无法下载")
                    else:
                        logger.info(f"[{bvid}] 播放器字幕仍为空（aid 已补齐）")

            # 最后兜底：从 view 接口的字幕列表里取
            view_subtitles = (video_info or {}).get("subtitle", {}).get("list") or []
            if view_subtitles:
                selected_subtitle = pick_subtitle(view_subtitles)
                subtitle_url = extract_url(selected_subtitle or {})
                if subtitle_url:
                    subtitle_text = await self.bili.download_subtitle(subtitle_url)
                    if subtitle_text and len(subtitle_text) >= 50:
                        preview = subtitle_text[:120].replace("\n", " ").strip()
                        logger.info(f"[{bvid}] 字幕获取成功(view兜底)，长度={len(subtitle_text)}，预览：{preview}")
                        return subtitle_text
                    logger.info(f"[{bvid}] 字幕内容过少，已忽略")
                else:
                    logger.info(f"[{bvid}] 字幕地址为空，无法下载")
            else:
                logger.info(f"[{bvid}] view 字幕列表为空，无法兜底")

            logger.info(f"[{bvid}] 没有可用字幕，回退到简介兜底")
            return None
            
        except Exception as e:
            logger.warning(f"[{bvid}] 获取字幕失败: {e}")
            return None
    
    async def fetch_all_videos_content(
        self, 
        videos: list, 
        progress_callback=None
    ) -> list[VideoContent]:
        """
        批量获取视频内容
        
        Args:
            videos: 视频列表，每个元素需包含 bvid, title (可选 cid)
            progress_callback: 进度回调函数 callback(current, total, video_title)
            
        Returns:
            VideoContent 列表
        """
        import asyncio
        
        results = []
        total = len(videos)
        
        for i, video in enumerate(videos):
            bvid = video.get("bvid") or video.get("bv_id")
            title = video.get("title", "")
            cid = video.get("cid") or video.get("id")
            
            if not bvid:
                logger.warning(f"跳过无效视频: {video}")
                continue
            
            try:
                content = await self.fetch_content(bvid, cid, title)
                results.append(content)
                
                if progress_callback:
                    progress_callback(i + 1, total, title)
                    
            except Exception as e:
                logger.error(f"处理视频失败 [{bvid}]: {e}")
                results.append(VideoContent(
                    bvid=bvid,
                    title=title or bvid,
                    content=f"处理失败: {str(e)}",
                    source=ContentSource.BASIC_INFO
                ))
            
            # 控制请求速率
            await asyncio.sleep(0.5)
        
        return results
