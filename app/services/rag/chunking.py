"""
增强规则分块模块

结构增强的规则语义分块：
1. 结构预处理：清理空白、保留段落、提取 outline 标题
2. 规则语义分段：按空行、标题模式、长句标点、outline 边界优先切分
3. 长度约束：目标 600-900 字符，overlap 80-150
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List
from loguru import logger


@dataclass
class ChunkResult:
    """分块结果"""
    display_text: str              # 原始展示文本
    embedding_text: str            # 用于 embedding 的增强文本（含标题前缀）
    section_title: Optional[str] = None
    content_type: str = "content"  # page_intro | content | outline | summary
    char_start: int = 0
    char_end: int = 0


class SemanticChunker:
    """
    语义分块器

    三层策略：
    1. 预处理 → 清理异常空白，保留段落结构
    2. 语义分段 → 按空行 / outline / 标题 / 长句标点 优先切分
    3. 长度约束 → 目标 600-900，过长段落内部滑动窗口切分
    """

    # 默认参数：比原 1000/200 更小更贴近主题边界
    DEFAULT_TARGET_SIZE = 750
    DEFAULT_MIN_SIZE = 300
    DEFAULT_MAX_SIZE = 900
    DEFAULT_OVERLAP = 100

    # 标题正则（用于语义分段）
    TITLE_PATTERN = re.compile(
        r"(?m)^(#{1,3}\s+|"
        r"第[一二三四五六七八九十\d]+[章节篇]\s*|"
        r"【[^】]+】\s*|"
        r"\d+\.\s+|"
        r"\d+、\s+)"
    )

    def __init__(
        self,
        target_size: int = DEFAULT_TARGET_SIZE,
        min_size: int = DEFAULT_MIN_SIZE,
        max_size: int = DEFAULT_MAX_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ):
        self.target_size = target_size
        self.min_size = min_size
        self.max_size = max_size
        self.overlap = overlap

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def chunk(
        self,
        text: str,
        video_title: str = "",
        page_title: Optional[str] = None,
        outline: Optional[List[dict]] = None,
    ) -> List[ChunkResult]:
        """
        对文本进行增强规则分块

        Args:
            text: 原始文本（ASR 或字幕）
            video_title: 视频标题
            page_title: 分P标题
            outline: 分段提纲（可选）

        Returns:
            ChunkResult 列表
        """
        # Phase 1: 预处理
        text = self._preprocess(text)
        if not text:
            logger.warning("[CHUNKING] 预处理后文本为空")
            return []

        # Phase 2: 语义分段
        segments = self._split_by_semantic_boundaries(text, outline)
        if not segments:
            logger.warning("[CHUNKING] 语义分段后无有效段")
            return []

        # Phase 3: 贪心合并相邻短段 + 对长段滑动窗口切分
        final_chunks = self._merge_and_split_segments(segments)
        if not final_chunks:
            return []

        # 生成 ChunkResult
        results: List[ChunkResult] = []
        global_pos = 0

        for chunk_text in final_chunks:
            section_title = self._detect_section_title(chunk_text, outline, page_title)
            content_type = self._detect_content_type(chunk_text, outline)
            embedding_text = self._build_embedding_text(
                chunk_text, video_title, page_title, section_title
            )

            char_start = global_pos
            char_end = global_pos + len(chunk_text)

            results.append(
                ChunkResult(
                    display_text=chunk_text,
                    embedding_text=embedding_text,
                    section_title=section_title,
                    content_type=content_type,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            global_pos = max(char_end - self.overlap, char_start + 1)

        logger.info(
            f"[CHUNKING] 原始文本 {len(text)} 字符 -> {len(results)} 个 chunk, "
            f"平均 {sum(len(c.display_text) for c in results) // max(len(results), 1)} 字符"
        )
        return results

    # ------------------------------------------------------------------
    # Phase 1: 预处理
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(text: str) -> str:
        """清理异常空白，保留段落结构"""
        if not text:
            return ""
        # 合并连续空白行（3+ 换行 → 2 换行）
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        # 行首行尾空白
        text = "\n".join(line.strip() for line in text.split("\n"))
        # 合并连续空格
        text = re.sub(r" +", " ", text)
        return text.strip()

    # ------------------------------------------------------------------
    # Phase 2: 语义分段
    # ------------------------------------------------------------------

    def _split_by_semantic_boundaries(
        self, text: str, outline: Optional[List[dict]]
    ) -> List[str]:
        """
        按语义边界切分，优先级：
        1. outline 标题边界（最强）
        2. 空行（段落边界）
        3. 标题模式
        4. 长句结束标点
        """
        # 1. 尝试按 outline 边界切分
        if outline:
            outline_segments = self._split_by_outline(text, outline)
            if len(outline_segments) > 1:
                return outline_segments

        # 2. 按空行（段落）切分
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return [text]

        # 3. 对过长段落进一步切分
        segments: List[str] = []
        for para in paragraphs:
            if len(para) > self.max_size:
                sub_segments = self._split_long_paragraph(para)
                segments.extend(sub_segments)
            else:
                segments.append(para)

        return segments

    def _split_by_outline(self, text: str, outline: List[dict]) -> List[str]:
        """按 outline 标题位置切分文本"""
        positions = [0]
        for item in outline:
            title = item.get("title", "")
            if not title:
                continue
            idx = text.find(title)
            if idx != -1:
                positions.append(idx)

        positions = sorted(set(positions))
        if len(positions) < 2:
            return []

        segments = []
        for i in range(len(positions)):
            start = positions[i]
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            seg = text[start:end].strip()
            if seg:
                segments.append(seg)
        return segments

    def _split_long_paragraph(self, para: str) -> List[str]:
        """对长段落按标题模式和长句标点切分"""
        # 先尝试标题模式
        parts = self.TITLE_PATTERN.split(para)
        if len(parts) > 1:
            merged = self._merge_split_parts(parts)
            if merged:
                return merged

        # 按句子切分
        sentences = self._split_to_sentences(para)
        if len(sentences) > 1:
            return sentences

        return [para]

    @staticmethod
    def _merge_split_parts(parts: List[str]) -> List[str]:
        """合并 re.split 的结果（分隔符与内容配对）"""
        merged: List[str] = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and parts[i + 1] and parts[i + 1][0] in "#第【0123456789":
                # 当前是内容，下一个是标题前缀
                merged.append(parts[i] + parts[i + 1])
                i += 2
            else:
                if parts[i].strip():
                    merged.append(parts[i])
                i += 1
        return merged

    # ------------------------------------------------------------------
    # Phase 3: 合并短段 + 切分长段
    # ------------------------------------------------------------------

    def _merge_and_split_segments(self, segments: List[str]) -> List[str]:
        """
        先贪心合并相邻短段到接近 target_size，再对过长的段滑动窗口切分。
        """
        if not segments:
            return segments

        # Step 1: 贪心合并相邻段
        merged: List[str] = []
        current = ""
        for seg in segments:
            if not current:
                current = seg
            elif len(current) + len(seg) <= self.target_size:
                current += "\n" + seg
            else:
                merged.append(current)
                current = seg
        if current:
            merged.append(current)

        # Step 2: 对过长段做滑动窗口切分
        final: List[str] = []
        for text in merged:
            if len(text) <= self.max_size:
                final.append(text)
            else:
                final.extend(self._split_long_text(text))

        return final

    def _split_long_text(self, text: str) -> List[str]:
        """对超长文本按句子滑动窗口切分"""
        sentences = self._split_to_sentences(text)
        if len(sentences) <= 1:
            return [text]

        chunks: List[str] = []
        i = 0
        while i < len(sentences):
            current = ""
            j = i
            while j < len(sentences) and len(current) + len(sentences[j]) <= self.target_size:
                current += sentences[j]
                j += 1

            if not current:
                current = sentences[j]
                j += 1

            chunks.append(current)

            # overlap：回退若干句子
            overlap_chars = 0
            k = j - 1
            while k > i and overlap_chars < self.overlap:
                overlap_chars += len(sentences[k])
                k -= 1
            i = k + 1 if k > i else j

        return chunks

    @staticmethod
    def _split_to_sentences(text: str) -> List[str]:
        """按句子结束标点切分，保留标点"""
        pattern = r"([。！？.!?]+)"
        parts = re.split(pattern, text)
        sentences: List[str] = []
        i = 0
        while i < len(parts):
            sent = parts[i]
            if i + 1 < len(parts) and parts[i + 1]:
                sent += parts[i + 1]
                i += 2
            else:
                i += 1
            if sent.strip():
                sentences.append(sent)
        return sentences

    # ------------------------------------------------------------------
    # Metadata 检测
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_section_title(
        text: str, outline: Optional[List[dict]], page_title: Optional[str]
    ) -> Optional[str]:
        """检测段落所属章节标题"""
        # 文本开头是否有标题模式
        m = re.match(r"^(?:#{1,3}\s+|【[^】]+】|\d+\.\s+)(.+?)[\n\r]", text)
        if m:
            return m.group(1).strip()

        # outline 中是否有标题出现在段落前部
        if outline:
            for item in outline:
                title = item.get("title", "")
                if title and title in text[:300]:
                    return title

        return page_title

    @staticmethod
    def _detect_content_type(text: str, outline: Optional[List[dict]]) -> str:
        """检测内容类型"""
        head = text[:80].lower()

        if outline and any(
            item.get("title", "") in text[:200] for item in outline
        ):
            return "outline"

        if re.search(r"^(总结|summary|结论|conclusion|收尾)", head):
            return "summary"

        if re.search(r"^(介绍|引言|intro|前言|开场|欢迎)", head):
            return "page_intro"

        return "content"

    # ------------------------------------------------------------------
    # Embedding 文本构造
    # ------------------------------------------------------------------

    @staticmethod
    def _build_embedding_text(
        chunk_text: str,
        video_title: str,
        page_title: Optional[str],
        section_title: Optional[str],
    ) -> str:
        """
        构造用于 embedding 的增强文本。

        格式：
            [page_title] | [video_title] | [section_title]
            [chunk body]
        """
        titles: List[str] = []
        for t in (page_title, video_title, section_title):
            if t and t.strip() and t.strip() not in titles:
                titles.append(t.strip())

        if titles:
            header = " | ".join(titles)
            return f"{header}\n{chunk_text.strip()}"
        return chunk_text.strip()


# ----------------------------------------------------------------------
# 便捷工厂函数
# ----------------------------------------------------------------------

def get_chunker(
    target_size: Optional[int] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    overlap: Optional[int] = None,
) -> SemanticChunker:
    """创建 SemanticChunker 实例，未传参数使用默认值"""
    kwargs = {}
    if target_size is not None:
        kwargs["target_size"] = target_size
    if min_size is not None:
        kwargs["min_size"] = min_size
    if max_size is not None:
        kwargs["max_size"] = max_size
    if overlap is not None:
        kwargs["overlap"] = overlap
    return SemanticChunker(**kwargs)
