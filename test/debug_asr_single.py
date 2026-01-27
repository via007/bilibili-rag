"""
单视频 ASR 诊断脚本

用途：
1. 针对指定 BV 号执行内容抓取（优先 ASR）
2. 输出关键日志与最终来源/长度，便于定位 403 与 ASR 失败原因
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import time
from http import HTTPStatus
from urllib import request as urlrequest
from urllib.parse import urlparse

from loguru import logger
import httpx
import dashscope
from dashscope.audio.asr import Transcription, Recognition
from dashscope.utils.oss_utils import OssUtils

from app.services.bilibili import BilibiliService
from app.services.asr import ASRService
from app.services.content_fetcher import ContentFetcher


def _get_output_value(output, key: str, default=None):
    if isinstance(output, dict):
        return output.get(key, default)
    if output is None:
        return default
    return getattr(output, key, default)


def _download_transcription(url: str) -> str | None:
    try:
        raw = urlrequest.urlopen(url).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"官方 ASR 结果下载失败: {e}")
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


async def _probe_audio_url(audio_url: str) -> int | None:
    """探测音频 URL 可达性（不带 Cookie）"""
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        status = None
        try:
            head = await client.head(audio_url)
            status = head.status_code
        except Exception as e:
            logger.info(f"音频 URL HEAD 失败: {e}")

        if status is None or status >= 400:
            try:
                headers = {"Range": "bytes=0-0"}
                get = await client.get(audio_url, headers=headers)
                status = get.status_code
            except Exception as e:
                logger.info(f"音频 URL GET 失败: {e}")
    return status


def _transcode_audio_to_wav(file_path: str) -> str | None:
    """使用 ffmpeg 转码为 16k 单声道 wav，提高 ASR 兼容性"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.info("未检测到 ffmpeg，跳过转码")
        return None

    base, _ext = os.path.splitext(file_path)
    wav_path = base + ".wav"
    cmd = [
        ffmpeg,
        "-y",
        "-i", file_path,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        wav_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            logger.warning(f"转码失败: {err[:200]}")
            return None
        return wav_path
    except Exception as e:
        logger.warning(f"转码异常: {e}")
        return None


def _transcode_audio_to_pcm(file_path: str) -> str | None:
    """转码为 16k s16le pcm，适配 Recognition"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.info("未检测到 ffmpeg，跳过转码")
        return None

    base, _ext = os.path.splitext(file_path)
    pcm_path = base + ".pcm"
    cmd = [
        ffmpeg,
        "-y",
        "-i", file_path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "16000",
        pcm_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            logger.warning(f"转码 PCM 失败: {err[:200]}")
            return None
        return pcm_path
    except Exception as e:
        logger.warning(f"转码 PCM 异常: {e}")
        return None


def _transcribe_official_sync(
    audio_url: str,
    model: str,
    api_key: str,
    base_url: str | None,
    timeout: int,
) -> str | None:
    """官方 SDK 转写（同步）"""
    if not api_key:
        logger.error("未配置 DASHSCOPE_API_KEY，无法转写")
        return None
    dashscope.api_key = api_key
    if base_url:
        dashscope.base_http_api_url = base_url

    kwargs = {}
    if "paraformer" in model:
        kwargs["language_hints"] = ["zh", "en"]

    try:
        resp = Transcription.async_call(
            model=model,
            file_urls=[audio_url],
            **kwargs,
        )
    except Exception as e:
        logger.warning(f"官方 ASR 提交失败: {e}")
        return None

    output = getattr(resp, "output", None)
    task_id = _get_output_value(output, "task_id")
    if not task_id:
        logger.warning("官方 ASR 未返回 task_id")
        return None
    logger.info(f"官方 ASR 任务已提交: task_id={task_id}")

    start = time.time()
    while True:
        status = _get_output_value(output, "task_status")
        if status in ("SUCCEEDED", "FAILED"):
            break
        if time.time() - start > timeout:
            logger.warning("官方 ASR 任务超时")
            return None
        time.sleep(1.5)
        resp = Transcription.fetch(task=task_id)
        output = getattr(resp, "output", None)

    status_code = getattr(resp, "status_code", None)
    if status_code != HTTPStatus.OK:
        logger.warning(f"官方 ASR 请求失败: status_code={status_code}")
        return None

    results = _get_output_value(output, "results", []) or []
    status_message = _get_output_value(output, "status_message")
    logger.info(
        "官方 ASR 任务状态: task_id={}, task_status={}, status_code={}, status_message={}, results={}",
        task_id,
        _get_output_value(output, "task_status"),
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
                "官方 ASR 子任务状态: task_id={}, subtask_status={}, has_url={}, error={}",
                task_id,
                sub_status,
                bool(transcription_url),
                error_message,
            )
        if sub_status == "SUCCEEDED" and transcription_url:
            return _download_transcription(transcription_url)

    logger.warning("官方 ASR 未返回有效转写结果")
    return None


async def _transcribe_official(
    audio_url: str,
    model: str,
    api_key: str,
    base_url: str | None,
    timeout: int,
) -> str | None:
    return await asyncio.to_thread(
        _transcribe_official_sync, audio_url, model, api_key, base_url, timeout
    )


async def _try_official_asr(
    bili: BilibiliService,
    bvid: str,
    cid: int,
    model: str,
    api_key: str,
    base_url: str | None,
    timeout: int,
) -> str | None:
    audio_url = await bili.get_audio_url(bvid, cid)
    if not audio_url:
        logger.info(f"[{bvid}] 未获取到音频 URL")
        return None

    status = await _probe_audio_url(audio_url)
    if status is not None:
        logger.info(f"[{bvid}] 音频 URL 可达性: {status}")
    if status is not None and status < 400:
        text = await _transcribe_official(audio_url, model, api_key, base_url, timeout)
        if text:
            return text

    logger.info(f"[{bvid}] 音频 URL 不可达，改用本地下载上传")
    tmp_dir = os.path.join("data", "asr_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    parsed = urlparse(audio_url)
    ext = os.path.splitext(parsed.path)[1] or ".m4s"
    filename = f"{bvid}_{cid}_{int(time.time())}{ext}"
    file_path = os.path.join(tmp_dir, filename)

    ok = await bili.download_audio_to_file(audio_url, file_path)
    if not ok:
        logger.warning(f"[{bvid}] 本地下载音频失败")
        return None

    upload_path = _transcode_audio_to_wav(file_path) or file_path
    try:
        oss_url = await asyncio.to_thread(
            OssUtils.upload,
            model=model,
            file_path=upload_path,
            api_key=api_key,
        )
        logger.info(f"[{bvid}] 官方 ASR 临时文件上传成功: {oss_url}")
    except Exception as e:
        logger.warning(f"[{bvid}] 官方 ASR 上传失败: {e}")
        oss_url = None

    for path in {file_path, upload_path}:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            logger.debug(f"[{bvid}] 清理本地文件失败: {path}")

    if not oss_url:
        return None

    return await _transcribe_official(oss_url, model, api_key, base_url, timeout)


async def run_once(bvid: str, cid: int | None = None, official_asr: bool = False,
                   model: str | None = None, timeout: int = 600,
                   recognition_asr: bool = False, rec_format: str = "wav") -> None:
    """执行一次抓取与 ASR 诊断"""
    sessdata = os.getenv("BILI_SESSDATA", "")
    bili_jct = os.getenv("BILI_JCT", "")
    dedeuserid = os.getenv("BILI_DEDEUSERID", "")

    bili = BilibiliService(
        sessdata=sessdata or None,
        bili_jct=bili_jct or None,
        dedeuserid=dedeuserid or None,
    )
    asr = ASRService()
    fetcher = ContentFetcher(bili, asr)

    try:
        video_info = await bili.get_video_info(bvid)
        title = video_info.get("title", "")
        resolved_cid = cid or video_info.get("cid")
        logger.info(f"[{bvid}] 标题: {title}")
        logger.info(f"[{bvid}] CID: {resolved_cid}")

        if recognition_asr:
            api_key = os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
            used_model = model or os.getenv("ASR_MODEL_LOCAL") or os.getenv("ASR_MODEL") or "paraformer-v1"
            logger.info(f"[{bvid}] Recognition 模型: {used_model}")
            if not api_key:
                logger.error("未配置 DASHSCOPE_API_KEY，无法转写")
            else:
                dashscope.api_key = api_key
                audio_url = await bili.get_audio_url(bvid, resolved_cid)
                if not audio_url:
                    logger.info(f"[{bvid}] 未获取到音频 URL")
                else:
                    logger.info(f"[{bvid}] Recognition 走本地下载 + 直传")
                    tmp_dir = os.path.join("data", "asr_tmp")
                    os.makedirs(tmp_dir, exist_ok=True)
                    parsed = urlparse(audio_url)
                    ext = os.path.splitext(parsed.path)[1] or ".m4s"
                    filename = f"{bvid}_{resolved_cid}_{int(time.time())}{ext}"
                    file_path = os.path.join(tmp_dir, filename)
                    ok = await bili.download_audio_to_file(audio_url, file_path)
                    if not ok:
                        logger.warning(f"[{bvid}] 本地下载音频失败")
                    else:
                        if rec_format == "pcm":
                            wav_path = _transcode_audio_to_pcm(file_path) or file_path
                        else:
                            wav_path = _transcode_audio_to_wav(file_path) or file_path
                        try:
                            recognizer = Recognition(
                                model=used_model,
                                callback=None,
                                format=rec_format,
                                sample_rate=16000,
                            )
                            result = recognizer.call(wav_path)
                            logger.info(
                                f"[{bvid}] Recognition 结果: status_code={getattr(result, 'status_code', None)} "
                                f"code={getattr(result, 'code', None)} message={getattr(result, 'message', None)} "
                                f"request_id={getattr(result, 'request_id', None)} output={getattr(result, 'output', None)}"
                            )
                            sentences = result.get_sentence() or []
                            texts = []
                            for s in sentences:
                                t = s.get("text") if isinstance(s, dict) else None
                                if t:
                                    texts.append(t)
                            text = "\n".join(texts).strip() if texts else None
                            if text:
                                preview = text[:200].replace("\n", " ").strip()
                                logger.info(f"[{bvid}] 最终来源: recognition_asr")
                                logger.info(f"[{bvid}] 文本长度: {len(text)}")
                                logger.info(f"[{bvid}] 文本预览: {preview}")
                            else:
                                logger.info(f"[{bvid}] Recognition 未返回文本")
                        except Exception as e:
                            logger.warning(f"[{bvid}] Recognition 异常: {e}")
                        finally:
                            for path in {file_path, wav_path}:
                                try:
                                    if path and os.path.exists(path):
                                        os.remove(path)
                                except Exception:
                                    logger.debug(f"[{bvid}] 清理本地文件失败: {path}")
        elif official_asr:
            api_key = os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
            base_url = os.getenv("DASHSCOPE_BASE_URL", "") or None
            used_model = model or os.getenv("ASR_MODEL_LOCAL") or os.getenv("ASR_MODEL") or "paraformer-v1"
            logger.info(f"[{bvid}] 官方 ASR 模型: {used_model}")
            text = await _try_official_asr(
                bili=bili,
                bvid=bvid,
                cid=resolved_cid,
                model=used_model,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
            if text:
                preview = text[:200].replace("\n", " ").strip()
                logger.info(f"[{bvid}] 最终来源: official_asr")
                logger.info(f"[{bvid}] 文本长度: {len(text)}")
                logger.info(f"[{bvid}] 文本预览: {preview}")
            else:
                logger.info(f"[{bvid}] 官方 ASR 失败，未返回文本")
        else:
            content = await fetcher.fetch_content(bvid, cid=resolved_cid, title=title)
            text = content.content or ""
            preview = text[:200].replace("\n", " ").strip()
            logger.info(f"[{bvid}] 最终来源: {content.source.value}")
            logger.info(f"[{bvid}] 文本长度: {len(text)}")
            logger.info(f"[{bvid}] 文本预览: {preview}")
    finally:
        await bili.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="单视频 ASR 诊断脚本")
    parser.add_argument("bvid", nargs="?", default="BV1M7nyzGE6j", help="B站 BV 号")
    parser.add_argument("--cid", type=int, default=None, help="可选：指定 CID")
    parser.add_argument("--official-asr", action="store_true", help="仅用官方 SDK 进行 ASR 直测")
    parser.add_argument("--recognition-asr", action="store_true", help="使用 Recognition 直传音频（不走 OSS）")
    parser.add_argument("--model", type=str, default=None, help="官方 ASR 模型（默认 paraformer-v1）")
    parser.add_argument("--rec-format", type=str, default="wav", choices=["wav", "pcm"],
                        help="Recognition 输入格式（wav 或 pcm）")
    parser.add_argument("--timeout", type=int, default=600, help="ASR 超时秒数")
    args = parser.parse_args()

    asyncio.run(run_once(
        args.bvid,
        args.cid,
        args.official_asr,
        args.model,
        args.timeout,
        args.recognition_asr,
        args.rec_format,
    ))


if __name__ == "__main__":
    main()
