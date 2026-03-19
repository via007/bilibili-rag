"""
Bilibili RAG 知识库系统
ASR 质量评估服务
"""
from dataclasses import dataclass
from typing import List, Optional
from loguru import logger

from app.services.asr_local import ASRResult
from app.config import settings


@dataclass
class QualityReport:
    """质量报告"""
    quality_score: float  # 综合评分 0-1
    quality_grade: str  # excellent/good/medium/poor
    flags: List[str]  # 问题标记
    confidence_avg: float
    confidence_min: float
    audio_quality: str  # good/medium/poor
    speech_ratio: float  # 语音占比
    suggestions: List[str]  # 改进建议


class ASRQualityService:
    """ASR 质量评估"""

    def __init__(self):
        self.thresholds = {
            "confidence_low": getattr(settings, "asr_low_confidence", 0.6),
            "confidence_medium": 0.8,
            "audio_quality_poor": 0.3,
            "duration_short": 5,
            "duration_long": 7200,
        }

    async def evaluate(
        self,
        asr_result: ASRResult,
        audio_duration: Optional[int] = None
    ) -> QualityReport:
        """
        评估 ASR 结果质量

        Args:
            asr_result: ASR 转写结果
            audio_duration: 音频时长（秒）

        Returns:
            QualityReport: 包含评分、问题标记、建议
        """
        flags = []
        suggestions = []

        # 1. 置信度评估
        confidence_avg = asr_result.confidence_avg
        confidence_min = asr_result.confidence_min

        if confidence_avg < self.thresholds["confidence_low"]:
            flags.append("low_confidence")
            suggestions.append("ASR 置信度较低，建议人工检查")
        elif confidence_avg < self.thresholds["confidence_medium"]:
            flags.append("medium_confidence")

        if confidence_min < 0.4:
            flags.append("very_low_confidence_segment")

        # 2. 时长评估
        duration = asr_result.duration
        if duration < self.thresholds["duration_short"]:
            flags.append("too_short")
            suggestions.append("音频时长过短，可能影响转写质量")
        elif duration > self.thresholds["duration_long"]:
            flags.append("too_long")
            suggestions.append("音频时长过长，建议分段处理")

        # 3. 字数评估
        word_count = asr_result.word_count
        if duration > 0:
            words_per_second = word_count / duration
            # 正常中文语音语速约 3-5 字/秒
            if words_per_second < 1:
                flags.append("low_word_density")
                suggestions.append("文字密度异常低，可能是静音或背景音乐")
            elif words_per_second > 10:
                flags.append("high_word_density")
                suggestions.append("文字密度异常高，可能存在识别错误")

        # 4. 句子数量评估
        sentence_count = len(asr_result.sentences)
        if sentence_count == 0:
            flags.append("no_sentences")
            suggestions.append("未能识别出任何句子")

        # 5. 计算综合评分
        quality_score = self._calculate_score(
            confidence_avg=confidence_avg,
            confidence_min=confidence_min,
            flags=flags,
            duration=duration,
            word_count=word_count,
        )

        # 6. 确定质量等级
        if quality_score >= 0.9:
            quality_grade = "excellent"
        elif quality_score >= 0.7:
            quality_grade = "good"
        elif quality_score >= 0.5:
            quality_grade = "medium"
        else:
            quality_grade = "poor"

        # 7. 评估音频质量（如果提供）
        audio_quality = "good"
        if audio_duration and duration > 0:
            speech_ratio = duration / audio_duration
            if speech_ratio < self.thresholds["audio_quality_poor"]:
                audio_quality = "poor"
                flags.append("audio_quality")
                suggestions.append("音频语音占比较低，可能有较多背景音")
            elif speech_ratio < 0.5:
                audio_quality = "medium"
        else:
            speech_ratio = 1.0

        return QualityReport(
            quality_score=quality_score,
            quality_grade=quality_grade,
            flags=flags,
            confidence_avg=confidence_avg,
            confidence_min=confidence_min,
            audio_quality=audio_quality,
            speech_ratio=speech_ratio,
            suggestions=suggestions,
        )

    def _calculate_score(
        self,
        confidence_avg: float,
        confidence_min: float,
        flags: List[str],
        duration: int,
        word_count: int,
    ) -> float:
        """计算综合质量评分"""
        score = 1.0

        # 置信度权重 60%
        confidence_score = (confidence_avg * 0.6 + confidence_min * 0.4)
        score *= confidence_score

        # 时长惩罚
        if duration < 10:
            score *= 0.7
        elif duration > 7200:
            score *= 0.9

        # 问题标记惩罚
        penalty_map = {
            "low_confidence": 0.7,
            "medium_confidence": 0.9,
            "very_low_confidence_segment": 0.8,
            "too_short": 0.6,
            "too_long": 0.9,
            "no_sentences": 0.1,
            "low_word_density": 0.7,
            "high_word_density": 0.8,
        }

        for flag in flags:
            if flag in penalty_map:
                score *= penalty_map[flag]

        return max(0, min(1, score))

    def is_quality_acceptable(self, quality_report: QualityReport) -> bool:
        """判断质量是否可接受"""
        threshold = getattr(settings, "asr_quality_threshold", 0.7)
        return quality_report.quality_score >= threshold


# 服务实例
_asr_quality_service: Optional[ASRQualityService] = None


def get_asr_quality_service() -> ASRQualityService:
    """获取 ASR 质量评估服务实例"""
    global _asr_quality_service
    if _asr_quality_service is None:
        _asr_quality_service = ASRQualityService()
    return _asr_quality_service
