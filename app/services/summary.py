"""
Bilibili RAG 知识库系统

摘要生成服务 - 视频内容结构化摘要
"""
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta

# Default to Beijing Timezone
BEIJING_TZ = timezone(timedelta(hours=8))
from typing import List, Optional
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_factory import get_llm_client


# 摘要生成提示词
SUMMARY_PROMPT = """你是一个专业的B站视频内容分析师。你的任务是对视频进行深度分析，生成高质量的结构化摘要，帮助用户快速了解视频内容和学习价值。

## 视频信息
视频标题：{title}

视频内容（字幕/转写）：
{content}

## 分析任务

请对视频内容进行深度分析，提取以下信息：

### 1. 详细简介（short_intro）
请详细、系统地总结视频的核心内容，长度约200-500字。
- 要点：全面、结构清晰、逻辑严密，能够作为视频内容的精炼替代或辅助提纲
- 内容：不仅要概括主旨，还要包含核心论点、关键事实与最终结论

### 2. 核心要点（key_points）
提取5-10个视频的核心知识点或关键内容点。
- 这些要点应该覆盖视频的主要话题和关键信息
- 每个要点用简短的名词短语或动宾短语表达
- 排序：从最重要到次重要

### 3. 目标受众（target_audience）
判断这个视频适合什么水平的观众：
- "零基础入门" - 完全没有基础的小白
- "初学者" - 有基本了解，需要入门引导
- "有一定基础" - 具备基础知识，需要进阶
- "进阶学习" - 有较深基础，需要深入内容
- "专业人群" - 需要专业知识的用户

### 4. 难度评级（difficulty_level）
- beginner（入门级）：基础概念、科普性质、简单操作
- intermediate（进阶级）：需要一定基础、有一定深度
- advanced（专业级）：专业内容、复杂概念、高级技巧

### 5. 标签（tags）
为视频打上3-8个标签，反映视频的主题和类型。
- 标签要具体、准确
- 可以包含：技术栈、应用领域、学习阶段、内容类型等

## 输出要求

请严格按照以下JSON格式输出，不要有任何额外内容：

```json
{
    "short_intro": "一句话简介",
    "key_points": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "target_audience": "目标受众",
    "difficulty_level": "难度级别",
    "tags": ["标签1", "标签2", "标签3"]
}
```

注意：
1. 只输出JSON，不要有"以下是分析结果"之类的开场白
2. key_points 至少5个，最多10个
3. tags 至少3个，最多8个
4. 确保JSON格式正确
"""


@dataclass
class VideoSummary:
    """视频摘要数据结构"""
    bvid: str
    short_intro: str = ""                    # 一句话简介（50字内）
    key_points: List[str] = field(default_factory=list)  # 关键要点（3-5个）
    target_audience: str = ""                # 适合人群
    difficulty_level: str = "intermediate"    # 难度级别: beginner/intermediate/advanced
    tags: List[str] = field(default_factory=list)        # 标签
    is_generated: bool = False               # 是否已生成
    generated_at: Optional[datetime] = None   # 生成时间
    created_at: datetime = field(default_factory=lambda: datetime.now(BEIJING_TZ))
    updated_at: datetime = field(default_factory=lambda: datetime.now(BEIJING_TZ))

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        # 转换 datetime 为字符串
        if self.generated_at:
            data["generated_at"] = self.generated_at.isoformat()
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data


class SummaryService:
    """
    摘要生成服务

    负责：
    1. 使用 LLM 生成视频结构化摘要
    2. 内容截断避免超出上下文限制
    3. JSON 解析与降级处理
    """

    # 内容截断长度（避免超出 LLM 上下文）
    MAX_CONTENT_LENGTH = 15000

    def __init__(self, temperature: float = 0.1):
        """
        初始化摘要服务

        Args:
            temperature: LLM 温度参数
        """
        # 使用工厂函数获取 LLM 客户端
        self.llm = get_llm_client(temperature=temperature)
        logger.info("SummaryService 初始化成功")

    async def generate_summary(
        self,
        title: str,
        content: str,
        bvid: str
    ) -> VideoSummary:
        """
        生成视频摘要

        Args:
            title: 视频标题
            content: 视频内容（字幕/转写）
            bvid: 视频 BV 号

        Returns:
            VideoSummary: 结构化摘要
        """
        logger.info(f"[{bvid}] 开始生成摘要")

        # 内容截断（避免超出 LLM 上下文）
        truncated_content = self._truncate_content(content)

        # 构建提示词 - 使用 replace 避免 JSON 格式冲突
        prompt_text = SUMMARY_PROMPT.replace("{title}", title or "未知标题").replace("{content}", truncated_content)

        # 调用 LLM 生成摘要
        try:
            result_text = await self._call_llm(prompt_text)
            logger.info(f"[{bvid}] LLM 调用成功，开始解析")

            # 解析 JSON
            summary_data = self._parse_json_response(result_text)

            # 构建返回对象
            summary = VideoSummary(
                bvid=bvid,
                short_intro=summary_data.get("short_intro", ""),
                key_points=summary_data.get("key_points", []),
                target_audience=summary_data.get("target_audience", ""),
                difficulty_level=self._normalize_difficulty(
                    summary_data.get("difficulty_level", "intermediate")
                ),
                tags=summary_data.get("tags", []),
                is_generated=True,
                generated_at=datetime.now(BEIJING_TZ),
                updated_at=datetime.now(BEIJING_TZ)
            )

            logger.info(
                f"[{bvid}] 摘要生成完成: "
                f"intro={summary.short_intro[:30]}..., "
                f"points={len(summary.key_points)}, "
                f"level={summary.difficulty_level}"
            )

            return summary

        except Exception as e:
            logger.error(f"[{bvid}] 摘要生成失败: {e}")
            # 返回空摘要
            return VideoSummary(
                bvid=bvid,
                is_generated=False,
                updated_at=datetime.now(BEIJING_TZ)
            )

    def _truncate_content(self, content: str) -> str:
        """
        截断内容避免超出 LLM 上下文

        Args:
            content: 原始内容

        Returns:
            截断后的内容
        """
        if not content:
            return ""

        if len(content) > self.MAX_CONTENT_LENGTH:
            truncated = content[:self.MAX_CONTENT_LENGTH]
            # 尝试寻找最后一个完整的句号或换行符作为截断点
            last_newline = truncated.rfind('\n')
            last_period = max(truncated.rfind('。'), truncated.rfind('.'))
            
            cut_index = max(last_newline, last_period)
            # 如果截断点没有丢弃太多内容（至少保留 80%），则应用智能截断
            if cut_index > self.MAX_CONTENT_LENGTH * 0.8:
                truncated = truncated[:cut_index + 1]
                
            logger.debug(f"内容截断: {len(content)} -> {len(truncated)} 字符")
            return truncated + "\n...(内容已截断)"

        return content

    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM 生成内容

        Args:
            prompt: 已格式化的提示词

        Returns:
            LLM 生成的文本
        """
        # 使用 ainvoke 替代过时的 agenerate
        messages = [HumanMessage(content=prompt)]
        result = await self.llm.ainvoke(messages)

        return result.content

    def _parse_json_response(self, response_text: str) -> dict:
        """
        解析 LLM 返回的 JSON 响应

        Args:
            response_text: LLM 返回的文本

        Returns:
            解析后的字典
        """
        # 方法1: 直接尝试解析
        try:
            # 去除可能的 markdown 代码块标记
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            pass

        # 方法2: 从文本中提取 JSON
        return self._extract_json_from_text(response_text)

    def _extract_json_from_text(self, text: str) -> dict:
        """
        从文本中提取 JSON 对象

        Args:
            text: 包含 JSON 的文本

        Returns:
            提取出的字典
        """
        # 尝试匹配 ```json ... ```
        match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试匹配 ```... ```
        match = re.search(r'```([\s\S]*?)```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试匹配 { ... }
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 无法解析，返回空字典
        logger.warning("无法从响应中提取 JSON，返回空字典")
        return {}

    def _normalize_difficulty(self, level: str) -> str:
        """
        标准化难度级别

        Args:
            level: 原始难度级别

        Returns:
            标准化后的级别
        """
        level_lower = level.lower().strip()

        # 映射关系
        if "beginner" in level_lower or "入门" in level_lower or "初级" in level_lower:
            return "beginner"
        elif "advanced" in level_lower or "高级" in level_lower or "进阶" in level_lower:
            return "advanced"
        else:
            return "intermediate"


# 全局服务实例
_summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """
    获取摘要服务实例（单例）

    Returns:
        SummaryService 实例
    """
    global _summary_service
    if _summary_service is None:
        _summary_service = SummaryService()
    return _summary_service
