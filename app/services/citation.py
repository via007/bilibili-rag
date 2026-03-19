"""
Bilibili RAG 知识库系统

引用来源高亮服务

在 LLM 生成的回答中直接标注引用来源，让用户知道答案来自哪个视频。
"""
import json
import re
from typing import List, Dict, Optional
from loguru import logger
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from app.services.llm_factory import get_llm_client


class CitationGenerator:
    """
    引用生成器

    核心功能：
    1. 在上下文中标记【来源1】、【来源2】...
    2. 让 LLM 在回答时标注来源
    3. 从答案中提取引用信息
    """

    def __init__(self, temperature: float = 0.5):
        """
        初始化引用生成器

        Args:
            temperature: LLM 温度参数
        """
        self.llm = get_llm_client(temperature=temperature)

        # 带引用的问答提示模板 - V1 版本
        self.cited_qa_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业、友好的知识库助手。基于用户收藏的B站视频内容帮助用户解答问题。

## 核心原则
1. **准确引用**：必须基于提供的视频内容回答，每句话都要有依据
2. **清晰结构**：回答要有逻辑层次，便于理解
3. **友好态度**：像朋友交流一样自然、有帮助

## 视频内容（已检索到的相关知识）
{context}

## 历史对话（用于理解上下文）
{history}

## 回答要求

### 1. 分析问题
先理解用户真正想知道什么。

### 2. 回答结构

**直接回答**
用最简洁的语言直接回答用户问题。

**详细解释**
- 解释"为什么"：背后的原理和原因
- 提供背景：帮助理解的知识储备
- 适当举例：用具体例子说明

**补充信息**
- 相关的注意事项
- 扩展知识或进阶内容

### 3. 引用标注（重要！）
- 每引用一个视频内容，用【来源N】标注
- 标注位置：引用的观点或信息后立即标注
- 示例：这个问题涉及多个知识点【来源1】【来源3】

### 4. 回答风格
- 避免过于正式或机械，保持自然对话感
- 不要过度展开，保持重点清晰
- 专业技术内容要准确

请开始回答："""),
            ("human", "问题：{question}")
        ])

    async def generate_with_citations(
        self,
        question: str,
        docs: List[Document],
        k: int = 5,
        history: Optional[List[dict]] = None
    ) -> Dict:
        """
        生成带引用的回答

        Args:
            question: 用户问题
            docs: 检索到的文档列表
            k: 使用的文档数量
            history: 可选，会话历史 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            {
                "answer": "回答内容，包含【来源N】标注",
                "sources": [
                    {"bvid": "...", "title": "...", "url": "..."}
                ],
                "has_citations": True
            }
        """
        if not docs:
            return {
                "answer": "没有找到相关内容来回答您的问题。",
                "sources": [],
                "has_citations": False
            }

        # 限制使用的文档数量
        selected_docs = docs[:k]

        # 构建带来源标记的上下文
        context = self._build_cited_context(selected_docs)

        # 构建历史对话字符串
        history_str = self._format_history(history) if history else "无历史对话"

        # 调用 LLM 生成回答
        try:
            chain = (
                {
                    "context": lambda _: context,
                    "history": lambda _: history_str,
                    "question": RunnablePassthrough()
                }
                | self.cited_qa_prompt
                | self.llm
                | StrOutputParser()
            )

            answer = await chain.ainvoke(question)

            # 提取引用
            sources = self._extract_sources(selected_docs)
            has_citations = len(sources) > 0

            return {
                "answer": answer,
                "sources": sources,
                "has_citations": has_citations
            }
        except Exception as e:
            logger.error(f"生成引用回答失败: {e}")
            return {
                "answer": f"生成回答时发生错误: {str(e)}",
                "sources": self._build_basic_sources(selected_docs),
                "has_citations": False
            }

    def _build_cited_context(self, docs: List[Document]) -> str:
        """
        构建带引用标记的上下文

        Args:
            docs: 文档列表

        Returns:
            带【来源N】标记的上下文字符串
        """
        context_parts = []
        for i, doc in enumerate(docs, 1):
            title = doc.metadata.get("title", "未知标题")
            content = doc.page_content.strip()

            if content:
                context_parts.append(
                    f"【来源{i}】标题: {title}\n内容: {content}"
                )

        return "\n\n---\n\n".join(context_parts)

    def _extract_sources(self, docs: List[Document]) -> List[Dict]:
        """
        从文档列表中提取来源信息

        Args:
            docs: 文档列表

        Returns:
            来源信息列表
        """
        # 使用字典去重，按 bvid + chunk_index 合并
        seen = {}
        sources = []

        for doc in docs:
            meta = doc.metadata or {}
            bvid = meta.get("bvid", "")
            chunk_index = meta.get("chunk_index", 0)
            key = f"{bvid}_{chunk_index}"

            if key not in seen and bvid:
                seen[key] = True
                sources.append({
                    "bvid": bvid,
                    "title": meta.get("title", "未知标题"),
                    "url": meta.get("url", f"https://www.bilibili.com/video/{bvid}")
                })

        return sources

    def _build_basic_sources(self, docs: List[Document]) -> List[Dict]:
        """
        构建基础来源列表（用于失败时）

        Args:
            docs: 文档列表

        Returns:
            来源信息列表
        """
        return self._extract_sources(docs)

    def _format_history(self, history: Optional[List[dict]]) -> str:
        """
        格式化历史对话为字符串

        Args:
            history: 历史对话列表 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            格式化的历史对话字符串
        """
        if not history:
            return "无历史对话"

        formatted = []
        for msg in history[-10:]:  # 最多保留最近10条对话
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                formatted.append(f"用户: {content}")
            else:
                # 简化 assistant 回复，去除引用标注
                simplified = content.split("【来源")[0] if content else ""
                formatted.append(f"助手: {simplified}")

        return "\n".join(formatted)


class CitationGeneratorV2:
    """
    引用生成器 V2 - 结构化输出版本

    使用 JSON 格式让 LLM 输出带引用的回答，
    可以更精确地控制引用格式。
    """

    def __init__(self, temperature: float = 0.3):
        """
        初始化引用生成器 V2

        Args:
            temperature: LLM 温度参数（较低温度更适合结构化输出）
        """
        self.llm = get_llm_client(temperature=temperature)

        # 结构化输出提示模板 - V2 版本
        self.structured_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个知识库助手，基于B站视频内容回答问题。

## 任务
根据下方提供的视频内容回答用户问题，并按 JSON 格式输出回答和引用来源。

## 多路召回说明
当前系统使用多路召回策略检索相关内容：
- **语义检索**：通过向量相似度匹配语义相关的内容
- **关键词检索**：通过关键词匹配精确查找相关内容
- **时间排序**：优先展示最近更新的内容

每段内容都标记了【来源N】编号，其中N对应下文中该内容的顺序。

## JSON 输出格式
```json
{
    "answer": "你的回答内容",
    "citations": [
        {"source_id": 1, "reason": "这个信息来自【来源1】的视频..."},
        {"source_id": 2, "reason": "这个内容来自【来源2】..."}
    ]
}
```

## 引用规则
- **source_id**: 对应【来源N】中的编号（如来源1对应source_id: 1）
- **reason**: 说明这个引用来自哪个视频的什么内容
- 如果不需要引用，citations 为空数组 []
- 直接输出 JSON，不要有其他内容
- 如果用户追问，结合【历史对话】理解上下文
- 禁止虚构 source_id，必须使用上下文中存在的来源编号

## 回答要求
1. 只使用提供的上下文中的信息，不要添加未经验证的内容
2. 如果用户追问，结合【历史对话】理解上下文
3. 回答要自然、友好、有条理

视频内容：
{context}

历史对话：
{history}"""),
            ("human", "问题：{question}\n\n请按 JSON 格式回答：")
        ])

    async def generate_with_citations(
        self,
        question: str,
        docs: List[Document],
        k: int = 5,
        history: Optional[List[dict]] = None
    ) -> Dict:
        """
        生成带引用的回答（结构化版本）

        Args:
            question: 用户问题
            docs: 检索到的文档列表
            k: 使用的文档数量
            history: 可选，会话历史 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            {
                "answer": "回答内容",
                "sources": [
                    {"bvid": "...", "title": "...", "url": "...", "reason": "..."}
                ],
                "has_citations": True
            }
        """
        if not docs:
            return {
                "answer": "没有找到相关内容来回答您的问题。",
                "sources": [],
                "has_citations": False
            }

        # 限制使用的文档数量
        selected_docs = docs[:k]

        # 构建上下文
        context = self._build_cited_context(selected_docs)

        # 构建历史对话字符串
        history_str = self._format_history(history) if history else "无历史对话"

        # 调用 LLM 生成回答
        try:
            chain = (
                {
                    "context": lambda _: context,
                    "history": lambda _: history_str,
                    "question": RunnablePassthrough()
                }
                | self.structured_prompt
                | self.llm
                | StrOutputParser()
            )

            response_text = await chain.ainvoke(question)

            # 解析 JSON
            result = self._parse_json_response(response_text)

            if result:
                # 构建完整的来源信息
                sources = self._build_full_sources(result.get("citations", []), selected_docs)

                return {
                    "answer": result.get("answer", response_text),
                    "sources": sources,
                    "has_citations": len(sources) > 0
                }
            else:
                # JSON 解析失败，降级到普通版本
                logger.warning("JSON 解析失败，降级到普通引用模式")
                generator = CitationGenerator()
                return await generator.generate_with_citations(question, selected_docs)

        except Exception as e:
            logger.error(f"生成结构化引用回答失败: {e}")
            # 降级到普通版本
            generator = CitationGenerator()
            return await generator.generate_with_citations(question, selected_docs)

    def _build_cited_context(self, docs: List[Document]) -> str:
        """构建带来源标记的上下文"""
        context_parts = []
        for i, doc in enumerate(docs, 1):
            title = doc.metadata.get("title", "未知标题")
            content = doc.page_content.strip()

            if content:
                context_parts.append(
                    f"【来源{i}】标题: {title}\n内容: {content}"
                )

        return "\n\n---\n\n".join(context_parts)

    def _format_history(self, history: Optional[List[dict]]) -> str:
        """
        格式化历史对话为字符串

        Args:
            history: 历史对话列表 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            格式化的历史对话字符串
        """
        if not history:
            return "无历史对话"

        formatted = []
        for msg in history[-10:]:  # 最多保留最近10条对话
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                formatted.append(f"用户: {content}")
            else:
                # 简化 assistant 回复，去除引用标注
                simplified = content.split("【来源")[0] if content else ""
                formatted.append(f"助手: {simplified}")

        return "\n".join(formatted)

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """
        解析 JSON 响应

        Args:
            text: LLM 返回的文本

        Returns:
            解析后的字典，如果解析失败返回 None
        """
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            return None

    def _build_full_sources(
        self,
        citations: List[Dict],
        docs: List[Document]
    ) -> List[Dict]:
        """
        构建完整的来源信息

        Args:
            citations: LLM 输出的引用列表
            docs: 文档列表

        Returns:
            完整的来源信息
        """
        if not citations:
            # 没有引用，返回所有文档作为来源
            return self._build_basic_sources(docs)

        sources = []
        for cit in citations:
            source_id = cit.get("source_id", 1)
            if isinstance(source_id, str):
                source_id = int(source_id)

            idx = source_id - 1  # 转换为 0 索引
            if 0 <= idx < len(docs):
                doc = docs[idx]
                meta = doc.metadata or {}
                sources.append({
                    "bvid": meta.get("bvid", ""),
                    "title": meta.get("title", "未知标题"),
                    "url": meta.get("url", ""),
                    "reason": cit.get("reason", "")
                })

        # 如果解析出的来源为空，使用基础来源
        if not sources:
            return self._build_basic_sources(docs)

        return sources

    def _build_basic_sources(self, docs: List[Document]) -> List[Dict]:
        """构建基础来源列表"""
        seen = {}
        sources = []

        for doc in docs:
            meta = doc.metadata or {}
            bvid = meta.get("bvid", "")
            key = bvid

            if key not in seen and bvid:
                seen[key] = True
                sources.append({
                    "bvid": bvid,
                    "title": meta.get("title", "未知标题"),
                    "url": meta.get("url", f"https://www.bilibili.com/video/{bvid}"),
                    "reason": ""
                })

        return sources


# 便捷函数
async def generate_cited_answer(
    question: str,
    docs: List[Document],
    version: int = 1,
    k: int = 5,
    history: Optional[List[dict]] = None
) -> Dict:
    """
    生成带引用的回答（便捷函数）

    Args:
        question: 用户问题
        docs: 检索到的文档列表
        version: 版本号（1 或 2）
        k: 使用的文档数量
        history: 可选，会话历史 [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        {
            "answer": "回答内容",
            "sources": [...],
            "has_citations": True
        }
    """
    if version == 2:
        generator = CitationGeneratorV2()
    else:
        generator = CitationGenerator()

    return await generator.generate_with_citations(question, docs, k, history)


# 导出
__all__ = [
    "CitationGenerator",
    "CitationGeneratorV2",
    "generate_cited_answer"
]
