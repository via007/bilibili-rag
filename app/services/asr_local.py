"""
Bilibili RAG 知识库系统
本地 ASR 服务 - Whisper.cpp / FunASR 轻量版
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from loguru import logger


@dataclass
class Sentence:
    """句子"""
    text: str
    start: float
    end: float
    confidence: float
    speaker_id: Optional[str] = None


@dataclass
class ASRResult:
    """ASR 结果"""
    text: str
    sentences: List[Sentence]
    confidence_avg: float
    confidence_min: float
    duration: int
    word_count: int


class ASRBackend(ABC):
    """ASR 后端抽象基类"""

    @abstractmethod
    async def load_model(self) -> bool:
        """加载模型"""
        pass

    @abstractmethod
    async def transcribe(self, audio_path: str) -> Optional[ASRResult]:
        """转写音频"""
        pass

    @abstractmethod
    async def transcribe_chunk(self, audio_path: str, start: float, end: float) -> Optional[str]:
        """转写音频片段"""
        pass


class WhisperBackend(ASRBackend):
    """Whisper.cpp 后端（轻量首选）"""

    def __init__(
        self,
        model_size: str = "base",  # tiny/base/small/medium/large
        language: str = "zh",  # 中文
        quantize: bool = True,  # 量化
    ):
        self.model_size = model_size
        self.language = language
        self.model = None
        self.quantize = quantize
        self._model_cache = {}  # 模型缓存

    async def load_model(self) -> bool:
        """加载 Whisper 模型"""
        try:
            from whispercpp import Whisper
            model_name = f"{self.model_size}.{self.quantize and 'q8' or 'fp16'}"
            if model_name not in self._model_cache:
                self._model_cache[model_name] = Whisper.from_pretrained(
                    self.model_size,
                    quantize=self.quantize
                )
            self.model = self._model_cache[model_name]
            logger.info(f"Whisper 模型加载成功: {model_name}")
            return True
        except Exception as e:
            logger.warning(f"Whisper 模型加载失败: {e}")
            return False

    async def transcribe(self, audio_path: str) -> Optional[ASRResult]:
        """转写音频"""
        if not self.model:
            loaded = await self.load_model()
            if not loaded:
                return None

        try:
            from whispercpp import Whisper

            # 分片处理（每 30 秒一片，避免内存溢出）
            result_text = self.model.transcribe(
                audio_path,
                language=self.language,
                chunk_length_s=30,  # 分片长度
            )

            # 提取段落信息
            segments = self.model.extract_segments(result_text)

            sentences = []
            for seg in segments:
                sentences.append(Sentence(
                    text=seg.get("text", ""),
                    start=seg.get("start", 0),
                    end=seg.get("end", 0),
                    confidence=seg.get("avg_logprob", 0.5),  # Whisper 用 logprob
                ))

            if not sentences:
                return None

            # 计算置信度（转换为 0-1）
            confidence_avg = self._logprob_to_confidence(
                sum(s.confidence for s in sentences) / len(sentences) if sentences else 0
            )

            return ASRResult(
                text="".join(s.text for s in sentences),
                sentences=sentences,
                confidence_avg=confidence_avg,
                confidence_min=confidence_avg,  # Whisper 不提供 per-segment
                duration=int(sentences[-1].end) if sentences else 0,
                word_count=len("".join(s.text for s in sentences)),
            )
        except Exception as e:
            logger.warning(f"Whisper 转写失败: {e}")
            return None

    def _logprob_to_confidence(self, logprob: float) -> float:
        """将 logprob 转换为置信度 0-1"""
        # logprob 通常在 -1 到 0 之间
        return max(0, min(1, (logprob + 1)))

    async def transcribe_chunk(self, audio_path: str, start: float, end: float) -> Optional[str]:
        """转写音频片段"""
        # TODO: 使用 ffmpeg 提取片段后转写
        pass


class FunASRBackend(ASRBackend):
    """FunASR 后端（效果好）"""

    def __init__(
        self,
        model_name: str = "paraformer-tiny",
        model_dir: Optional[str] = None,
    ):
        from app.config import settings
        self.model_name = model_name
        self.model_dir = model_dir or settings.funasr_model_dir
        self.model = None

    async def load_model(self) -> bool:
        """加载 FunASR 模型"""
        try:
            from funasr import AutoModel
            self.model = AutoModel(
                model=self.model_name,
                model_dir=self.model_dir,
                device="cpu",  # 默认 CPU
            )
            logger.info(f"FunASR 模型加载成功: {self.model_name}")
            return True
        except Exception as e:
            logger.warning(f"FunASR 模型加载失败: {e}")
            return False

    async def transcribe(self, audio_path: str) -> Optional[ASRResult]:
        """转写音频"""
        if not self.model:
            loaded = await self.load_model()
            if not loaded:
                return None

        try:
            result = self.model.generate(
                input=audio_path,
                batch_size_s=300,  # 批处理时长
            )

            # 解析结果
            sentences = []
            for item in result:
                text = item.get("text", "")
                timestamp = item.get("timestamp", [])
                sentences.append(Sentence(
                    text=text,
                    start=timestamp[0] if timestamp else 0,
                    end=timestamp[-1] if len(timestamp) > 1 else 0,
                    confidence=item.get("score", 0.8),
                ))

            if not sentences:
                return None

            return ASRResult(
                text="".join(s.text for s in sentences),
                sentences=sentences,
                confidence_avg=sum(s.confidence for s in sentences) / len(sentences) if sentences else 0,
                confidence_min=min(s.confidence for s in sentences) if sentences else 0,
                duration=int(sentences[-1].end) if sentences else 0,
                word_count=len("".join(s.text for s in sentences)),
            )
        except Exception as e:
            logger.warning(f"FunASR 转写失败: {e}")
            return None

    async def transcribe_chunk(self, audio_path: str, start: float, end: float) -> Optional[str]:
        """转写音频片段"""
        # TODO: 使用 ffmpeg 提取片段后转写
        pass


class LocalASRService:
    """本地 ASR 统一服务"""

    def __init__(
        self,
        backend: str = "whisper",  # whisper / funasr
        **kwargs,
    ):
        self.backend_name = backend
        self.backend: Optional[ASRBackend] = None
        self._init_backend(backend, **kwargs)

    def _init_backend(self, backend: str, **kwargs):
        """初始化后端"""
        if backend == "whisper":
            self.backend = WhisperBackend(**kwargs)
        elif backend == "funasr":
            self.backend = FunASRBackend(**kwargs)
        else:
            raise ValueError(f"不支持的后端: {backend}")

    async def transcribe(self, audio_path: str) -> Optional[ASRResult]:
        """转写音频"""
        if not self.backend:
            raise RuntimeError("ASR 后端未初始化")
        return await self.backend.transcribe(audio_path)

    async def load_model(self) -> bool:
        """预加载模型"""
        if not self.backend:
            return False
        return await self.backend.load_model()


# 服务实例缓存
_local_asr_service: Optional[LocalASRService] = None


def get_local_asr_service() -> Optional[LocalASRService]:
    """获取本地 ASR 服务实例（需要先配置 ASR_MODE=local 或 auto）"""
    global _local_asr_service
    if _local_asr_service is None:
        # 延迟初始化，避免启动时加载模型
        from app.config import settings

        if settings.asr_mode in ("local", "auto"):
            try:
                _local_asr_service = LocalASRService(
                    backend=settings.asr_backend,
                    model_size=settings.whisper_model_size,
                    language=settings.whisper_language,
                    quantize=settings.whisper_quantize,
                    model_name=settings.funasr_model,
                    device=settings.funasr_device,
                )
                logger.info(f"本地 ASR 服务初始化成功，后端: {settings.asr_backend}")
            except Exception as e:
                logger.warning(f"本地 ASR 服务初始化失败: {e}")
                return None
        else:
            return None
    return _local_asr_service
