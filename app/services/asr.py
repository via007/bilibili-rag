"""
Bilibili RAG 知识库系统

ASR 服务 - 使用 DashScope 录音文件识别
"""
import asyncio
import json
import os
import time
from http import HTTPStatus
from typing import Optional, Any
from urllib import request as urlrequest

import dashscope
from dashscope.audio.asr import Transcription
from dashscope.utils.oss_utils import OssUtils
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
        logger.info(f"ASR 任务已提交: task_id={task_id}")

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
        status_message = self._get_output_value(output, "status_message")
        logger.info(
            "ASR 任务状态: task_id={}, task_status={}, status_code={}, status_message={}, results={}",
            task_id,
            self._get_output_value(output, "task_status"),
            status_code,
            status_message,
            len(results),
        )
        for item in results:
            sub_status = item.get("subtask_status")
            transcription_url = item.get("transcription_url")
            error_message = item.get("error_message") or item.get("message")
            if sub_status:
                logger.info(
                    "ASR 子任务状态: task_id={}, subtask_status={}, has_url={}, error={}",
                    task_id,
                    sub_status,
                    bool(transcription_url),
                    error_message,
                )
            if sub_status == "SUCCEEDED" and transcription_url:
                return self._download_transcription(item["transcription_url"])

        logger.warning("ASR 未返回有效转写结果")
        return None

    def _upload_temp_file(self, file_path: str) -> Optional[str]:
        """上传本地文件到 DashScope 临时 OSS，返回 oss:// URL"""
        self._configure()
        if not os.path.exists(file_path):
            logger.warning(f"ASR 本地文件不存在: {file_path}")
            return None
        try:
            oss_url = OssUtils.upload(
                model=self.model,
                file_path=file_path,
                api_key=self.api_key,
            )
            logger.info(f"ASR 临时文件上传成功: {oss_url}")
            return oss_url
        except Exception as e:
            logger.warning(f"ASR 临时文件上传失败: {e}")
            return None

    async def transcribe_url(self, audio_url: str) -> Optional[str]:
        return await asyncio.to_thread(self._transcribe_sync, audio_url)

    async def transcribe_local_file(self, file_path: str) -> Optional[str]:
        """上传本地文件后进行转写"""
        try:
            oss_url = await asyncio.to_thread(self._upload_temp_file, file_path)
            if not oss_url:
                return None
            return await asyncio.to_thread(self._transcribe_sync, oss_url)
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                logger.debug(f"ASR 临时文件清理失败: {file_path}")
