"""
Bilibili RAG 知识库系统

ASR 服务 - 使用 DashScope 录音文件识别
"""
import asyncio
import json
import time
from http import HTTPStatus
from typing import Optional, Any
from urllib import request as urlrequest

import dashscope
from dashscope.audio.asr import Transcription
from loguru import logger

from app.config import settings


class ASRService:
    """音频转文字服务（DashScope）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or getattr(settings, "dashscope_base_url", None)
        self.model = model or getattr(settings, "asr_model", "fun-asr")
        self.timeout = timeout or getattr(settings, "asr_timeout", 600)

    def _configure(self) -> None:
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE API Key")
        dashscope.api_key = self.api_key
        if self.base_url:
            dashscope.base_http_api_url = self.base_url

    def _get_output_value(self, output: Any, key: str, default=None):
        if isinstance(output, dict):
            return output.get(key, default)
        return getattr(output, key, default)

    def _download_transcription(self, url: str) -> Optional[str]:
        try:
            raw = urlrequest.urlopen(url).read().decode("utf-8")
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"ASR 结果下载失败: {e}")
            return None

        texts = []
        transcripts = data.get("transcripts") or []
        for item in transcripts:
            text = item.get("text", "") or ""
            if text:
                texts.append(text)
                continue
            for s in item.get("sentences", []) or []:
                s_text = s.get("text", "") or ""
                if s_text:
                    texts.append(s_text)

        if not texts and isinstance(data.get("text"), str):
            texts.append(data["text"])

        return "\n".join(texts).strip() if texts else None

    def _transcribe_sync(self, audio_url: str) -> Optional[str]:
        self._configure()

        kwargs = {}
        if "paraformer" in self.model:
            kwargs["language_hints"] = ["zh", "en"]

        try:
            resp = Transcription.async_call(
                model=self.model,
                file_urls=[audio_url],
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"ASR 提交失败: {e}")
            return None

        output = getattr(resp, "output", None)
        task_id = self._get_output_value(output, "task_id")
        if not task_id:
            logger.warning("ASR 未返回 task_id")
            return None

        start = time.time()
        while True:
            status = self._get_output_value(output, "task_status")
            if status in ("SUCCEEDED", "FAILED"):
                break
            if time.time() - start > self.timeout:
                logger.warning("ASR 任务超时")
                return None
            time.sleep(1.5)
            resp = Transcription.fetch(task=task_id)
            output = getattr(resp, "output", None)

        status_code = getattr(resp, "status_code", None)
        if status_code != HTTPStatus.OK:
            logger.warning(f"ASR 请求失败: status_code={status_code}")
            return None

        results = self._get_output_value(output, "results", []) or []
        for item in results:
            if item.get("subtask_status") == "SUCCEEDED" and item.get("transcription_url"):
                return self._download_transcription(item["transcription_url"])

        logger.warning("ASR 未返回有效转写结果")
        return None

    async def transcribe_url(self, audio_url: str) -> Optional[str]:
        return await asyncio.to_thread(self._transcribe_sync, audio_url)
