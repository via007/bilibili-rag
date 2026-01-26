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

import httpx
import dashscope
from dashscope.audio.asr import Transcription
from dashscope.common.utils import default_headers, join_url
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
        self.local_model = getattr(settings, "asr_model_local", self.model)

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

    def _build_api_url(self, *parts: str) -> str:
        base_url = self.base_url or getattr(dashscope, "base_http_api_url", None)
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/api/v1"
        return join_url(base_url, *parts)

    def _submit_transcription_task_restful(self, audio_url: str, model: str) -> Optional[str]:
        url = self._build_api_url("services", "audio", "asr", "transcription")
        headers = {
            **default_headers(self.api_key),
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        parameters = {}
        if "paraformer" in model:
            parameters["language_hints"] = ["zh", "en"]
        payload = {"model": model, "input": {"file_urls": [audio_url]}}
        if parameters:
            payload["parameters"] = parameters

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.warning(f"ASR RESTful 提交失败: {e}")
            return None

        if resp.status_code != HTTPStatus.OK:
            logger.warning(f"ASR RESTful 提交失败: status_code={resp.status_code}, body={resp.text[:300]}")
            return None

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            output = data.get("output") if isinstance(data, dict) else None
            if isinstance(output, dict):
                task_id = output.get("task_id")
        return task_id

    def _fetch_transcription_task_restful(self, task_id: str) -> Optional[dict]:
        url = self._build_api_url("tasks", task_id)
        headers = default_headers(self.api_key)
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
        except Exception as e:
            logger.warning(f"ASR RESTful 查询失败: {e}")
            return None

        if resp.status_code != HTTPStatus.OK:
            logger.warning(f"ASR RESTful 查询失败: status_code={resp.status_code}, body={resp.text[:300]}")
            return None

        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("output"), dict):
            return data["output"]
        return data if isinstance(data, dict) else None

    def _transcribe_sync_restful(self, audio_url: str, model: str) -> Optional[str]:
        self._configure()
        task_id = self._submit_transcription_task_restful(audio_url, model)
        if not task_id:
            logger.warning("ASR RESTful 未返回 task_id")
            return None
        logger.info(f"ASR 任务已提交(RESTful): task_id={task_id}")

        start = time.time()
        output = None
        while True:
            if time.time() - start > self.timeout:
                logger.warning("ASR 任务超时(RESTful)")
                return None
            output = self._fetch_transcription_task_restful(task_id)
            if not output:
                time.sleep(1.5)
                continue
            status = self._get_output_value(output, "task_status")
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(1.5)

        results = self._get_output_value(output, "results", []) or []
        status_message = self._get_output_value(output, "status_message")
        logger.info(
            "ASR 任务状态(RESTful): task_id={}, task_status={}, status_code={}, status_message={}, results={}",
            task_id,
            self._get_output_value(output, "task_status"),
            HTTPStatus.OK,
            status_message,
            len(results),
        )
        for item in results:
            sub_status = item.get("subtask_status")
            transcription_url = item.get("transcription_url")
            error_message = item.get("error_message") or item.get("message")
            if sub_status:
                logger.info(
                    "ASR 子任务状态(RESTful): task_id={}, subtask_status={}, has_url={}, error={}",
                    task_id,
                    sub_status,
                    bool(transcription_url),
                    error_message,
                )
            if sub_status == "SUCCEEDED" and transcription_url:
                return self._download_transcription(transcription_url)

        logger.warning("ASR 未返回有效转写结果(RESTful)")
        return None

    def _transcribe_sync(self, audio_url: str) -> Optional[str]:
        self._configure()
        if audio_url.startswith("oss://"):
            return self._transcribe_sync_restful(audio_url, self.model)

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

    def _upload_temp_file(self, file_path: str, model: Optional[str] = None) -> Optional[str]:
        """上传本地文件到 DashScope 临时 OSS，返回 oss:// URL"""
        self._configure()
        if not os.path.exists(file_path):
            logger.warning(f"ASR 本地文件不存在: {file_path}")
            return None
        try:
            upload_model = model or self.local_model or self.model
            oss_url = OssUtils.upload(
                model=upload_model,
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
        """上传本地文件后进行转写（使用本地模型）"""
        try:
            oss_url = await asyncio.to_thread(self._upload_temp_file, file_path, self.local_model)
            if not oss_url:
                return None
            return await asyncio.to_thread(self._transcribe_sync_with_model, oss_url, self.local_model)
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                logger.debug(f"ASR 临时文件清理失败: {file_path}")

    def _transcribe_sync_with_model(self, audio_url: str, model: str) -> Optional[str]:
        """使用指定模型转写（用于本地文件上传）"""
        if audio_url.startswith("oss://"):
            return self._transcribe_sync_restful(audio_url, model)
        original_model = self.model
        try:
            self.model = model
            return self._transcribe_sync(audio_url)
        finally:
            self.model = original_model
