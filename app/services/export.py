"""
Bilibili RAG 知识库系统
导出服务 - 将内容导出为 Markdown 格式
"""
import json
import re
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import VideoCache, ChatSession, ChatMessage, FavoriteVideo


class ExportService:
    """导出服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_video(self, bvid: str, format: str = "full") -> dict:
        """
        导出单个视频

        Args:
            bvid: 视频BV号
            format: 格式类型 "full" | "simple"

        Returns:
            包含 filename, content, size 的字典
        """
        stmt = select(VideoCache).where(VideoCache.bvid == bvid)
        result = await self.db.execute(stmt)
        video = result.scalar_one_or_none()

        if not video:
            raise ValueError(f"视频不存在: {bvid}")

        content = self._generate_video_markdown(video, format)
        filename = f"video_{bvid}_{datetime.now().strftime('%Y%m%d')}.md"

        return {
            "filename": filename,
            "content": content,
            "size": len(content.encode('utf-8'))
        }

    async def export_folder(self, folder_id: int, format: str = "full") -> dict:
        """
        导出整个收藏夹

        Args:
            folder_id: 收藏夹 media_id
            format: 格式类型 "full" | "simple"

        Returns:
            包含 filename, content, size 的字典
        """
        from app.models import FavoriteFolder

        # 先通过 media_id 找到 FavoriteFolder 的主键 id
        stmt = select(FavoriteFolder).where(FavoriteFolder.media_id == folder_id)
        result = await self.db.execute(stmt)
        folder = result.scalar_one_or_none()

        if not folder:
            raise ValueError(f"收藏夹不存在: {folder_id}")

        actual_folder_id = folder.id
        folder_name = folder.title

        # 查询收藏夹中的所有视频
        stmt = select(VideoCache).join(
            FavoriteVideo, FavoriteVideo.bvid == VideoCache.bvid
        ).where(
            and_(
                FavoriteVideo.folder_id == actual_folder_id,
                VideoCache.is_processed == True
            )
        )
        result = await self.db.execute(stmt)
        videos = result.scalars().all()

        if not videos:
            # 如果没有关联表，直接查询所有已处理视频
            stmt = select(VideoCache).where(VideoCache.is_processed == True)
            result = await self.db.execute(stmt)
            videos = result.scalars().all()

        contents = []
        for video in videos:
            content = self._generate_video_markdown(video, format)
            contents.append(content)

        full_content = "\n\n---\n\n".join(contents)
        filename = f"folder_{folder_id}_{datetime.now().strftime('%Y%m%d')}.md"

        return {
            "filename": filename,
            "content": full_content,
            "size": len(full_content.encode('utf-8'))
        }

    async def export_folders(self, folder_ids: List[int], format: str = "full") -> dict:
        """
        导出多个收藏夹

        Args:
            folder_ids: 收藏夹ID列表
            format: 格式类型 "full" | "simple"

        Returns:
            包含 filename, content, size 的字典
        """
        from app.models import FavoriteFolder

        # 获取收藏夹信息（media_id -> id 映射）
        stmt = select(FavoriteFolder).where(FavoriteFolder.media_id.in_(folder_ids))
        result = await self.db.execute(stmt)
        folder_objs = list(result.scalars().all())
        folders = {f.id: f.title for f in folder_objs}
        # 同时保留 media_id 映射用于返回
        media_id_to_title = {f.media_id: f.title for f in folder_objs}

        logger.info(f"导出收藏夹: folder_ids={folder_ids}, 找到收藏夹数={len(folder_objs)}")
        logger.info(f"收藏夹详情: {[(f.id, f.media_id, f.title) for f in folder_objs]}")

        # 收集所有视频内容
        all_contents = []

        for folder_id in folder_ids:
            # folder_id 在这里是 media_id，需要转换为 FavoriteFolder.id
            # 找到对应的 FavoriteFolder.id
            actual_folder_id = None
            for f in folder_objs:
                if f.media_id == folder_id:
                    actual_folder_id = f.id
                    break

            if not actual_folder_id:
                logger.warning(f"未找到收藏夹 media_id={folder_id}")
                continue

            folder_name = media_id_to_title.get(folder_id, f"收藏夹{folder_id}")

            # 先检查 FavoriteVideo 中有多少视频
            fv_stmt = select(FavoriteVideo).where(FavoriteVideo.folder_id == actual_folder_id)
            fv_result = await self.db.execute(fv_stmt)
            favorite_videos = list(fv_result.scalars().all())
            logger.info(f"收藏夹 {folder_name} (id={actual_folder_id}) 关联视频数: {len(favorite_videos)}")

            # 查询该收藏夹中的所有已处理视频
            # 注意：FavoriteVideo.folder_id 关联的是 FavoriteFolder.id，不是 media_id
            stmt = select(VideoCache).join(
                FavoriteVideo, FavoriteVideo.bvid == VideoCache.bvid
            ).where(
                and_(
                    FavoriteVideo.folder_id == actual_folder_id,
                    VideoCache.is_processed == True
                )
            )
            result = await self.db.execute(stmt)
            videos = list(result.scalars().all())
            logger.info(f"收藏夹 {folder_name} 已处理视频数: {len(videos)}")

            if not videos:
                continue

            # 添加收藏夹标题
            folder_content = [f"## {folder_name}\n"]

            for video in videos:
                content = self._generate_video_markdown(video, format)
                folder_content.append(content)

            all_contents.append("\n\n---\n\n".join(folder_content))

        if not all_contents:
            raise ValueError("所选收藏夹中没有已处理的内容")

        # 合并所有内容
        full_content = "\n\n---\n\n".join(all_contents)
        filename = f"folders_{len(folder_ids)}个_{datetime.now().strftime('%Y%m%d')}.md"

        return {
            "filename": filename,
            "content": full_content,
            "size": len(full_content.encode('utf-8'))
        }

    async def export_session(self, chat_session_id: str) -> dict:
        """
        导出会话

        Args:
            chat_session_id: 会话ID

        Returns:
            包含 filename, content, size 的字典
        """
        # 获取会话信息
        stmt = select(ChatSession).where(ChatSession.session_id == chat_session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"会话不存在: {chat_session_id}")

        # 获取会话消息
        stmt = select(ChatMessage).where(
            ChatMessage.chat_session_id == chat_session_id
        ).order_by(ChatMessage.created_at)
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        content = self._generate_session_markdown(session, messages)
        filename = f"session_{chat_session_id[:8]}_{datetime.now().strftime('%Y%m%d')}.md"

        return {
            "filename": filename,
            "content": content,
            "size": len(content.encode('utf-8'))
        }

    async def export_session_summary(self, chat_session_id: str, format: str = "full") -> dict:
        """
        导出会话总结（AI 知识点提取）

        Args:
            chat_session_id: 会话ID
            format: 格式类型 "full" | "simple"

        Returns:
            包含 filename, content, size 的字典
        """
        # 获取会话信息
        stmt = select(ChatSession).where(ChatSession.session_id == chat_session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"会话不存在: {chat_session_id}")

        # 获取会话中所有 AI 回答
        stmt = select(ChatMessage).where(
            and_(
                ChatMessage.chat_session_id == chat_session_id,
                ChatMessage.role == "assistant"
            )
        ).order_by(ChatMessage.created_at)
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        if not messages:
            raise ValueError("会话中没有 AI 回答")

        # 提取所有回答内容
        all_content = []
        all_sources = []
        for msg in messages:
            if msg.content:
                all_content.append(msg.content)
            if msg.sources:
                all_sources.extend(msg.sources)

        # 合并内容（限制长度以免超出 LLM 上下文）
        combined_content = "\n\n---\n\n".join(all_content)
        if len(combined_content) > 8000:
            combined_content = combined_content[:8000] + "..."

        # 去重来源
        unique_sources = {}
        for s in all_sources:
            bvid = s.get("bvid") if isinstance(s, dict) else None
            if bvid and bvid not in unique_sources:
                unique_sources[bvid] = s

        # 调用 LLM 提取知识点
        knowledge_data = await self._extract_knowledge(combined_content)

        # 生成 Markdown
        content = self._generate_summary_markdown(session, knowledge_data, unique_sources, format)
        filename = f"总结_{session.title or chat_session_id[:8]}_{datetime.now().strftime('%Y%m%d')}.md"

        return {
            "filename": filename,
            "content": content,
            "size": len(content.encode('utf-8'))
        }

    async def get_session_summary(self, chat_session_id: str) -> dict:
        """
        获取会话总结（优先缓存）

        Args:
            chat_session_id: 会话ID

        Returns:
            包含 has_cache, data 的字典
        """
        from app.models import SessionSummary
        from sqlalchemy import select, desc

        # 1. 查询最新缓存
        stmt = select(SessionSummary).where(
            SessionSummary.chat_session_id == chat_session_id
        ).order_by(desc(SessionSummary.version)).limit(1)
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()

        if summary:
            return {
                "success": True,
                "has_cache": True,
                "data": {
                    "content": summary.content,
                    "version": summary.version,
                    "source_video_count": summary.source_video_count,
                    "message_count": summary.message_count,
                    "created_at": summary.created_at.isoformat() if summary.created_at else None,
                    "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
                }
            }

        # 2. 无缓存，调用 LLM 生成
        content_data = await self._generate_summary_content(chat_session_id, "full")

        # 3. 存入缓存
        summary = SessionSummary(
            chat_session_id=chat_session_id,
            content=content_data["content"],
            version=1,
            source_video_count=content_data.get("source_video_count", 0),
            message_count=content_data.get("message_count", 0),
            token_used=content_data.get("token_used", 0),
        )
        self.db.add(summary)
        await self.db.commit()

        return {
            "success": True,
            "has_cache": False,
            "data": {
                "content": summary.content,
                "version": summary.version,
                "source_video_count": summary.source_video_count,
                "message_count": summary.message_count,
                "created_at": summary.created_at.isoformat() if summary.created_at else None,
                "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
            }
        }

    async def refresh_session_summary(self, chat_session_id: str, format: str = "full") -> dict:
        """
        刷新会话总结（重新生成）

        Args:
            chat_session_id: 会话ID
            format: 格式类型

        Returns:
            包含 regenerated, data 的字典
        """
        from app.models import SessionSummary
        from sqlalchemy import select, desc

        # 1. 获取旧版本号
        stmt = select(SessionSummary).where(
            SessionSummary.chat_session_id == chat_session_id
        ).order_by(desc(SessionSummary.version)).limit(1)
        result = await self.db.execute(stmt)
        old_summary = result.scalar_one_or_none()
        old_version = old_summary.version if old_summary else 0

        # 2. 删除旧缓存
        if old_summary:
            await self.db.delete(old_summary)
            await self.db.commit()

        # 3. 调用 LLM 生成新总结
        content_data = await self._generate_summary_content(chat_session_id, format)

        # 4. 存入新缓存
        new_summary = SessionSummary(
            chat_session_id=chat_session_id,
            content=content_data["content"],
            version=old_version + 1,
            source_video_count=content_data.get("source_video_count", 0),
            message_count=content_data.get("message_count", 0),
            token_used=content_data.get("token_used", 0),
        )
        self.db.add(new_summary)
        await self.db.commit()

        return {
            "success": True,
            "regenerated": True,
            "data": {
                "content": new_summary.content,
                "version": new_summary.version,
                "source_video_count": new_summary.source_video_count,
                "message_count": new_summary.message_count,
                "created_at": new_summary.created_at.isoformat() if new_summary.created_at else None,
                "updated_at": new_summary.updated_at.isoformat() if new_summary.updated_at else None,
            }
        }

    async def delete_session_summary(self, chat_session_id: str) -> None:
        """删除会话总结缓存"""
        from app.models import SessionSummary
        from sqlalchemy import delete

        stmt = delete(SessionSummary).where(
            SessionSummary.chat_session_id == chat_session_id
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _generate_summary_content(self, chat_session_id: str, format: str) -> dict:
        """生成总结内容（内部方法）"""
        # 获取会话信息
        stmt = select(ChatSession).where(ChatSession.session_id == chat_session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"会话不存在: {chat_session_id}")

        # 获取会话中所有 AI 回答
        stmt = select(ChatMessage).where(
            and_(
                ChatMessage.chat_session_id == chat_session_id,
                ChatMessage.role == "assistant"
            )
        ).order_by(ChatMessage.created_at)
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        if not messages:
            raise ValueError("会话中没有 AI 回答")

        # 提取所有回答内容
        all_content = []
        all_sources = []
        for msg in messages:
            if msg.content:
                all_content.append(msg.content)
            if msg.sources:
                all_sources.extend(msg.sources)

        # 合并内容
        combined_content = "\n\n---\n\n".join(all_content)
        if len(combined_content) > 8000:
            combined_content = combined_content[:8000] + "..."

        # 去重来源
        unique_sources = {}
        for s in all_sources:
            bvid = s.get("bvid") if isinstance(s, dict) else None
            if bvid and bvid not in unique_sources:
                unique_sources[bvid] = s

        # 调用 LLM 提取知识点
        knowledge_data = await self._extract_knowledge(combined_content)

        # 生成 Markdown
        content = self._generate_summary_markdown(session, knowledge_data, unique_sources, format)

        return {
            "content": content,
            "source_video_count": len(unique_sources),
            "message_count": len(messages),
            "token_used": len(combined_content) // 4,  # 估算
        }

    async def _extract_knowledge(self, content: str) -> dict:
        """调用 LLM 提取知识点"""
        from app.services.llm_factory import get_llm_client

        prompt = """# 任务：AI 对话知识深度提取与结构化

你是资深的技术知识整理专家，擅长从 AI 对话中深度提取有价值的知识点，进行系统性归类和详细阐述。

## 输入内容
以下是某次 AI 对话中，AI 对用户问题的详细回答汇总：
{content}

## 你的任务
从以上 AI 回答中**全面深度提取**所有核心知识点，去除冗余信息，按主题归类，生成详尽的知识总结。

## 输出要求

### 必须严格遵循以下 JSON 格式：
```json
{{
  "summary": "整体总结，80-150字，概括本次对话的核心主题、技术范围和价值",
  "categories": [
    {{
      "name": "分类名称（如：Python 基础语法 / 线性代数向量 / Spring Cloud 微服务 / Docker 容器化）",
      "points": [
        {{"content": "核心知识点，30-50字，包含完整的概念定义", "detail": "50-100字的详细说明，包含背景、用途、实现方式、注意事项等"}},
        {{"content": "下一个核心知识点", "detail": "详细说明"}},
        {{"content": "再下一个核心知识点", "detail": "详细说明"}}
      ]
    }}
  ],
  "sources": []
}}
```

## 提取规范（重要！）

### 1. 全面提取原则
- 提取 AI 回答中的**所有**事实性知识点，不遗漏任何有价值的信息
- 区分**概念定义**、**使用方法**、**注意事项**、**最佳实践**、**常见问题**
- 每个知识点都要有**详细说明**，不能只给一句话

### 2. 深度归类规则
- 按**技术主题**或**知识领域**归类（如：语法、数据类型、框架、算法、工具、安装、配置等）
- **每个分类至少 3-5 个要点**，要点数量根据内容深度决定
- 分类名称要**简洁准确**，使用领域通用术语
- 如果内容丰富，可以分成多个相关分类

### 3. 详细说明要求
- **content**：30-50字，包含完整的概念定义或核心操作
- **detail**：50-100字，详细说明，包含：
  - 背景和原理
  - 使用场景和用途
  - 具体实现方式或代码示例
  - 注意事项和常见坑
  - 相关知识点对比

### 4. 精简但详细
- 不要车轱辘话，但每个要点都要有实质性内容
- 避免空洞的概括，提供具体的知识点
- detail 是重点，要写得详尽

## 禁止出现的内容

❌ 客套话：
- "下面为您介绍..."
- "很高兴为您解答..."
- "希望对您有所帮助..."

❌ 冗余表达：
- "需要注意的是..."（直接说明内容）
- "总的来说..."（直接给出结论）
- "总之..."（直接给出要点）

❌ 未经验证的信息：
- "可能是..."
- "大概..."
- "据说..."

## 输出格式

请**只输出 JSON 字符串**，不要包含任何解释、markdown 代码块标记、注释或前言后语。

**记住：内容越详尽越好！**"""

        text = ""  # 初始化变量
        try:
            from langchain_core.messages import HumanMessage

            client = get_llm_client()

            # 最多重试 2 次
            for attempt in range(2):
                text = ""  # 每次重试前重置
                try:
                    # 替换占位符
                    final_prompt = prompt.replace("{content}", content)
                    messages = [HumanMessage(content=final_prompt)]

                    # 使用 ainvoke 代替 agenerate，确保获取完整响应
                    response = await client.ainvoke(messages)
                    text = response.content if response else ""
                    logger.info(f"LLM 原始输出 (attempt {attempt + 1}): {text[:500]}")

                    # 提取 JSON
                    text = text.strip()

                    # 清理 markdown 代码块标记
                    text = text.replace("```json", "").replace("```", "")

                    # 清理开头的 {{ （这是 prompt 转义导致的）
                    while text.startswith("{{"):
                        text = text[1:]
                    while text.startswith("}}"):
                        text = text[2:]

                    # 清理 SQL 等杂质（从第一个 { 之后的内容）
                    first_brace = text.find('{')
                    if first_brace > 0:
                        text = text[first_brace:]

                    # 清理任何非 JSON 内容（从最后一个 } 截断）
                    last_brace = text.rfind('}')
                    if last_brace > 0:
                        text = text[:last_brace + 1]

                    # 清理重复内容（如 "categories": [ ... categories": [）
                    if text.count("categories") > 1:
                        first_idx = text.find('"categories"')
                        second_idx = text.find('"categories"', first_idx + 1)
                        if second_idx > 0:
                            text = text[:second_idx]
                            # 补全缺失的括号
                            text = self._fix_incomplete_json(text)

                    # 确保以 { 开头
                    text = text.strip()
                    if not text.startswith("{"):
                        # 查找第一个 {
                        first_brace = text.find("{")
                        if first_brace > 0:
                            text = text[first_brace:]

                    # 使用安全的 JSON 提取
                    data = self._extract_json_safely(text)

                    # 验证结构
                    if "categories" not in data:
                        data["categories"] = []
                    if "summary" not in data:
                        data["summary"] = ""
                    if "sources" not in data:
                        data["sources"] = []

                    return data

                except json.JSONDecodeError as e:
                    logger.warning(f"JSON 解析失败 (attempt {attempt + 1}): {e}")
                    if attempt == 0:
                        # 第一次失败，尝试简化 prompt 再试一次
                        content = content[:3000]  # 截断内容减少长度
                        continue
                    else:
                        raise

            # 不应该到达这里
            raise Exception("重试后仍失败")

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"知识提取失败: {e}, 原始输出: {text[:500] if text else 'empty'}")
            # 使用安全的 JSON 提取作为回退
            if text:
                return self._extract_json_safely(text)
            return {
                "summary": "知识提取失败，请查看原始对话记录",
                "categories": [],
                "sources": []
            }

    def _fix_incomplete_json(self, text: str) -> str:
        """修复截断的 JSON（补全缺失的括号）"""
        import re

        # 尝试用正则提取完整的 JSON 对象
        # 匹配从第一个 { 到最后一个 }
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            text = match.group(0)

        # 统计括号数量
        open_braces = text.count('{')
        close_braces = text.count('}')
        open_brackets = text.count('[')
        close_brackets = text.count(']')

        # 补全大括号
        if open_braces > close_braces:
            missing = open_braces - close_braces
            text += '}' * missing

        # 补全中括号
        if open_brackets > close_brackets:
            missing = open_brackets - close_brackets
            text += ']' * missing

        return text

    def _extract_json_safely(self, text: str) -> dict:
        """安全提取 JSON，失败则返回默认结构"""
        import re

        text = text.strip()

        # 移除 markdown 代码块
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'```$', '', text)

        # 移除 {{ 和 }}
        text = text.replace('{{', '{').replace('}}', '}')

        # 确保以 { 开始
        first_brace = text.find('{')
        if first_brace > 0:
            text = text[first_brace:]

        # 尝试提取 JSON
        try:
            # 补全截断的 JSON
            text = self._fix_incomplete_json(text)
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 回退：使用正则提取
        result = {"summary": "", "categories": [], "sources": []}

        # 提取 summary（支持多行）
        summary_match = re.search(r'"summary"\s*:\s*"([^"]*(?:[^"\\]*\\.[^"]*)*)"', text, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1)

        return result

    def _generate_summary_markdown(self, session: ChatSession, knowledge: dict, sources: dict, format: str) -> str:
        """生成总结 Markdown"""
        lines = []

        # 标题
        title = session.title or "会话总结"
        lines.append(f"# {title}")
        lines.append("")

        # 元信息
        video_count = len(sources)
        created_at = session.created_at.strftime('%Y-%m-%d') if session.created_at else '未知'
        lines.append(f"> 来源: {video_count} 个视频 · {created_at}")
        lines.append("")

        # 整体总结
        summary = knowledge.get("summary", "")
        if summary:
            lines.append("## 整体总结")
            lines.append("")
            lines.append(summary)
            lines.append("")

        # 核心知识点
        categories = knowledge.get("categories", [])
        if categories:
            lines.append("## 核心知识点")
            lines.append("")

            for cat in categories:
                cat_name = cat.get("name", "")
                points = cat.get("points", [])
                if cat_name and points:
                    lines.append(f"### {cat_name}")
                    lines.append("")
                    for p in points:
                        content = p.get("content", "")
                        detail = p.get("detail", "")
                        if detail:
                            lines.append(f"- {content}（{detail}）")
                        else:
                            lines.append(f"- {content}")
                    lines.append("")

        # 相关视频
        if sources:
            lines.append("## 相关视频")
            lines.append("")
            for bvid, s in sources.items():
                title = s.get("title", bvid) if isinstance(s, dict) else bvid
                url = s.get("url", f"https://www.bilibili.com/video/{bvid}") if isinstance(s, dict) else f"https://www.bilibili.com/video/{bvid}"
                lines.append(f"- [{title}]({url})")
            lines.append("")

        return "\n".join(lines)

    def _generate_video_markdown(self, video: VideoCache, format: str) -> str:
        """生成视频的 Markdown 内容"""
        lines = []

        # 标题
        lines.append(f"# {video.title}")
        lines.append("")

        # 元信息
        meta_parts = []
        if video.owner_name:
            meta_parts.append(f"作者: {video.owner_name}")
        if video.duration:
            minutes = video.duration // 60
            seconds = video.duration % 60
            meta_parts.append(f"时长: {minutes}:{seconds:02d}")

        if meta_parts:
            lines.append(f"> {' | '.join(meta_parts)}")
            lines.append("")

        # 摘要
        if video.content:
            # 使用摘要或内容的前500字作为摘要
            summary = video.content[:500] if len(video.content) > 500 else video.content
            lines.append("## 摘要")
            lines.append("")
            lines.append(summary)
            lines.append("")

        # 精简格式只到这里
        if format == "simple":
            # 添加核心要点（如果有提纲）
            if video.outline_json:
                lines.append("## 核心要点")
                lines.append("")
                for item in video.outline_json:
                    title = item.get('title', '')
                    if title:
                        lines.append(f"- {title}")
                lines.append("")
            return "\n".join(lines)

        # 完整格式 - 内容提纲
        if video.outline_json:
            lines.append("## 内容提纲")
            lines.append("")
            for item in video.outline_json:
                title = item.get('title', '')
                points = item.get('points', [])
                if title:
                    lines.append(f"### {title}")
                    lines.append("")
                    for point in points:
                        point_content = point.get('content', '')
                        if point_content:
                            lines.append(f"- {point_content}")
                    lines.append("")

        # 完整格式 - 原文内容
        if video.content:
            lines.append("## 原文内容")
            lines.append("")
            lines.append(video.content)
            lines.append("")

        return "\n".join(lines)

    def _generate_session_markdown(self, session: ChatSession, messages: List[ChatMessage]) -> str:
        """生成会话的 Markdown 内容"""
        lines = []

        # 标题
        lines.append(f"# {session.title or '会话'}")
        lines.append("")

        # 元信息
        created_at = session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else '未知'
        lines.append(f"> 创建时间: {created_at}")
        lines.append("")

        # 对话记录
        lines.append("## 对话记录")
        lines.append("")

        for i, msg in enumerate(messages):
            role = "用户" if msg.role == "user" else "AI回答"
            lines.append(f"### {role}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

            # 如果有来源，添加来源信息
            if msg.sources:
                source_bvids = [s.get('bvid', '') for s in msg.sources if s.get('bvid')]
                if source_bvids:
                    lines.append(f"*来源: {', '.join(source_bvids)}*")
                    lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
