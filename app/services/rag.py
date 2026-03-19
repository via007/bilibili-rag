"""
Bilibili RAG 知识库系统

RAG 服务模块 - 向量存储与问答
"""
from typing import List, Optional
from loguru import logger
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from app.config import settings
from app.models import VideoContent
from app.services.llm_factory import get_llm_client, get_embeddings_client


class RAGService:
    """
    RAG 服务
    
    负责：
    1. 向量存储管理
    2. 文档添加与检索
    3. 问答功能
    """
    
    def __init__(self, collection_name: str = "bilibili_videos"):
        """
        初始化 RAG 服务
        
        Args:
            collection_name: 向量集合名称
        """
        self.collection_name = collection_name
        
        # 初始化 Embeddings (使用工厂函数)
        self.embeddings = get_embeddings_client()
        logger.info("使用工厂函数初始化 Embeddings 成功")

        # 初始化向量存储
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=settings.chroma_persist_directory
        )

        # 初始化 LLM (使用工厂函数)
        self.llm = get_llm_client(temperature=0.5)
        
        # 文本分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "]
        )
        
        # 问答提示模板 - 支持多路召回和引用
        self.qa_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业、友好的知识库助手。你的任务是基于用户收藏的B站视频内容，帮助用户解答问题、学习知识。

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
先理解用户真正想知道什么，如果问题模糊，可以先确认用户意图。

### 2. 回答结构
请按以下结构回答：

**直接回答**
用最简洁的语言直接回答用户问题，不要绕弯子。

**详细解释**
- 解释"为什么"：背后的原理和原因
- 提供背景：帮助理解的知识储备
- 适当举例：用具体例子说明抽象概念

**补充信息**
- 相关的注意事项
- 扩展知识或进阶内容
- 如果适用，推荐相关视频

### 3. 引用标注（重要！）
- 每引用一个视频内容，用【来源N】标注，N是内容对应的编号
- 标注位置：引用的观点或信息后立即标注
- 示例：这个问题涉及多个知识点【来源1】【来源3】，而另一个观点则认为...【来源2】

### 4. 回答风格
- 避免过于正式或机械，保持自然对话感
- 专业技术内容要准确，日常话题可以轻松些
- 不要过度展开，保持重点清晰

### 5. 特殊情况处理
- 如果知识库中没有相关内容：明确告知用户，并提供合理建议
- 如果问题超出内容范围：基于常识回答，同时说明这一点
- 如果用户追问：结合前文上下文理解真正意图

请开始回答："""),
            ("human", "问题：{question}")
        ])
        
        # 无内容时的通用回复模板
        self.fallback_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个友好的助手。用户在使用一个B站收藏夹知识库系统。

当前情况：知识库中没有找到与用户问题相关的内容。

请：
1. 友好地回应用户的问题
2. 如果能根据常识简单回答，可以简要回答
3. 建议用户构建更多收藏夹内容，或者换个问法
4. 保持自然、不要死板
"""),
            ("human", "{question}")
        ])
        
        # 摘要提示模板
        self.summary_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个内容总结专家。请对以下视频字幕内容进行总结。

要求：
1. 提取核心要点（3-5个）
2. 生成一段简洁的总结（100-200字）
3. 保持原意，不要添加额外信息

字幕内容："""),
            ("human", "{content}")
        ])
    
    def add_video_content(self, video: VideoContent) -> int:
        """
        添加单个视频内容到向量库
        
        Args:
            video: VideoContent 对象
            
        Returns:
            添加的文档块数量
        """
        # 构建完整内容（正文不带标题，避免标题相似度主导召回）
        title = video.title or "未知标题"
        content_parts: List[str] = []
        
        if video.content and video.content.strip():
            content_parts.append(video.content.strip())
        
        # 如果有分段提纲，添加结构化信息
        if video.outline:
            outline_text = "\n## 内容提纲\n"
            for item in video.outline:
                item_title = item.get('title', '') or ''
                outline_text += f"\n### {item_title}\n"
                for point in item.get("points", []):
                    point_content = point.get('content', '') or ''
                    if point_content:
                        outline_text += f"- {point_content}\n"
            if outline_text.strip() != "## 内容提纲":
                content_parts.append(outline_text)
        
        full_content = "\n\n".join(content_parts).strip()
        
        # 验证内容不为空
        if not full_content or len(full_content.strip()) < 10:
            logger.warning(f"[{video.bvid}] 内容太少，跳过")
            return 0
        
        # 分块
        chunks = self.text_splitter.split_text(full_content)
        
        if not chunks:
            logger.warning(f"[{video.bvid}] 没有生成文档块")
            return 0
        
        # 过滤空内容块
        valid_chunks = [c for c in chunks if c and c.strip() and len(c.strip()) > 5]
        if not valid_chunks:
            logger.warning(f"[{video.bvid}] 没有有效的文档块")
            return 0
        
        # 创建文档
        documents = []
        for i, chunk in enumerate(valid_chunks):
            doc = Document(
                page_content=chunk.strip(),  # 确保是干净的字符串
                metadata={
                    "bvid": video.bvid,
                    "title": title,
                    "source": video.source.value,
                    "chunk_index": i,
                    "url": f"https://www.bilibili.com/video/{video.bvid}"
                }
            )
            documents.append(doc)
        
        # 添加到向量库
        try:
            batch_size = 10
            for idx in range(0, len(documents), batch_size):
                self.vectorstore.add_documents(documents[idx:idx + batch_size])
            logger.info(f"[{video.bvid}] 添加了 {len(documents)} 个文档块")
        except Exception as e:
            logger.error(f"[{video.bvid}] 添加到向量库失败: {e}")
            raise
        
        return len(documents)
    
    def add_videos_batch(self, videos: List[VideoContent], progress_callback=None) -> dict:
        """
        批量添加视频到向量库
        
        Args:
            videos: VideoContent 列表
            progress_callback: 进度回调 callback(current, total, title)
            
        Returns:
            {"success": 成功数, "failed": 失败数, "chunks": 总块数}
        """
        success = 0
        failed = 0
        total_chunks = 0
        
        for i, video in enumerate(videos):
            try:
                chunks = self.add_video_content(video)
                total_chunks += chunks
                success += 1
                
                if progress_callback:
                    progress_callback(i + 1, len(videos), video.title)
                    
            except Exception as e:
                logger.error(f"添加视频失败 [{video.bvid}]: {e}")
                failed += 1
        
        return {
            "success": success,
            "failed": failed,
            "chunks": total_chunks
        }
    
    def search(self, query: str, k: int = 5, bvids: Optional[List[str]] = None) -> List[Document]:
        """
        检索相关内容
        """
        if not query or not query.strip():
            logger.warning("检索查询为空")
            return []
            
        try:
            if bvids:
                docs = self.vectorstore.similarity_search(query, k=k, filter={"bvid": {"$in": bvids}})
            else:
                docs = self.vectorstore.similarity_search(query, k=k)

            logger.info(f"检索完成：query='{query}'，召回={len(docs)}")
            for idx, doc in enumerate(docs):
                meta = doc.metadata or {}
                title = meta.get("title", "")
                bvid = meta.get("bvid", "")
                chunk_index = meta.get("chunk_index", "")
                preview = doc.page_content[:120].replace("\n", " ").strip()
                logger.info(f"召回[{idx+1}] {bvid} #{chunk_index} {title} | {preview}")

            return docs
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []
    
    async def _fallback_answer(self, question: str, reason: str = "") -> dict:
        """
        当没有检索到内容时，让 AI 自然回复

        Args:
            question: 用户问题
            reason: 原因说明

        Returns:
            回答结果
        """
        try:
            chain = (
                {"question": RunnablePassthrough()}
                | self.fallback_prompt
                | self.llm
                | StrOutputParser()
            )

            answer = await chain.ainvoke(question)
            return {
                "answer": answer,
                "sources": []
            }
        except Exception as e:
            logger.error(f"Fallback 回复失败: {e}")
            return {
                "answer": f"抱歉，{reason}。您可以尝试构建更多收藏夹内容，或者换个问法试试。",
                "sources": []
            }

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

    async def answer_question(
        self,
        question: str,
        k: int = 5,
        bvids: Optional[List[str]] = None,
        history: Optional[List[dict]] = None
    ) -> dict:
        """
        回答问题

        Args:
            question: 用户问题
            k: 检索文档数量
            bvids: 可选，限制在这些视频范围内搜索
            history: 可选，会话历史 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            {
                "answer": 回答内容,
                "sources": 来源视频列表
            }
        """
        # 先检查向量库是否有内容
        stats = self.get_collection_stats()
        if stats["total_chunks"] == 0:
            # 知识库为空时，使用 fallback 让 AI 自然回复
            return await self._fallback_answer(question, "知识库目前还没有内容")
        
        # 检索相关文档
        try:
            docs = self.search(question, k=k, bvids=bvids if bvids else None)
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return await self._fallback_answer(question, f"检索时遇到问题")
        
        if not docs:
            # 没检索到内容时，也让 AI 自然回复
            return await self._fallback_answer(question, "没有找到相关内容")
        
        # 构建上下文
        context_parts = []
        seen_bvids = set()
        sources = []
        
        for doc in docs:
            bvid = doc.metadata.get("bvid", "")
            title = doc.metadata.get("title", "未知标题")
            content = doc.page_content.strip()
            
            if content:  # 只添加有内容的文档
                context_parts.append(f"【{title}】\n{content}")
            
            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                sources.append({
                    "bvid": bvid,
                    "title": title,
                    "url": doc.metadata.get("url", f"https://www.bilibili.com/video/{bvid}")
                })
        
        # 如果没有有效内容
        if not context_parts:
            return {
                "answer": "检索到了相关视频，但没有找到有效的文本内容。可能是视频还未完成内容提取。",
                "sources": sources
            }
        
        context = "\n\n---\n\n".join(context_parts)

        # 确保 context 不为空
        if not context.strip():
            return {
                "answer": "没有找到可用的内容来回答您的问题。",
                "sources": sources
            }

        # 构建历史对话字符串
        history_str = self._format_history(history) if history else "无历史对话"

        # 构建链并执行
        try:
            chain = (
                {
                    "context": lambda _: context,
                    "history": lambda _: history_str,
                    "question": RunnablePassthrough()
                }
                | self.qa_prompt
                | self.llm
                | StrOutputParser()
            )

            answer = await chain.ainvoke(question)
            
            return {
                "answer": answer,
                "sources": sources
            }
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                "answer": f"AI 回答时发生错误: {str(e)}",
                "sources": sources
            }
    
    async def summarize_content(self, content: str) -> str:
        """
        使用 LLM 总结内容（用于字幕内容）
        
        Args:
            content: 原始内容（字幕文本）
            
        Returns:
            总结后的内容
        """
        # 如果内容太长，先截断
        max_length = 10000
        if len(content) > max_length:
            content = content[:max_length] + "\n...(内容已截断)"
        
        chain = (
            {"content": RunnablePassthrough()}
            | self.summary_prompt
            | self.llm
            | StrOutputParser()
        )
        
        return await chain.ainvoke(content)
    
    def get_collection_stats(self) -> dict:
        """
        获取向量库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            collection = self.vectorstore._collection
            count = collection.count()
            
            # 获取唯一视频数
            result = collection.get(include=["metadatas"])
            bvids = set()
            for meta in result.get("metadatas", []):
                if meta and "bvid" in meta:
                    bvids.add(meta["bvid"])
            
            return {
                "total_chunks": count,
                "total_videos": len(bvids),
                "collection_name": self.collection_name
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_chunks": 0,
                "total_videos": 0,
                "collection_name": self.collection_name
            }
    
    def clear_collection(self):
        """清空向量库"""
        try:
            self.vectorstore._collection.delete(where={})
            logger.info(f"已清空向量库: {self.collection_name}")
        except Exception as e:
            logger.error(f"清空向量库失败: {e}")
            raise
    
    def delete_video(self, bvid: str):
        """
        删除指定视频的所有文档块

        Args:
            bvid: 视频 BV 号
        """
        try:
            # 获取该视频的所有文档 ID
            collection = self.vectorstore._collection
            results = collection.get(where={"bvid": bvid}, include=["ids"])

            if results and results.get("ids"):
                # 根据 ID 删除文档
                collection.delete(ids=results["ids"])
                logger.info(f"已删除视频 {bvid} 的 {len(results['ids'])} 个文档块")
            else:
                logger.info(f"视频 {bvid} 在向量库中不存在")
        except Exception as e:
            logger.error(f"删除视频失败 [{bvid}]: {e}")
            raise
