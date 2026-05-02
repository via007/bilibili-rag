"""
Quiz 题目生成服务 — 批量生成练习题。

从 ChromaDB 检索知识片段，通过 LLM 批量生成题目，复用现有凭证管理体系。
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select
from langchain_openai import ChatOpenAI

from app.config import settings
from app.database import get_db_context
from app.models import QuizSet, FavoriteVideo
from app.services.rag import RAGService
from app.services.llm.buffered_usage_writer import get_buffered_usage_writer
from app.services.llm.usage_tracker import UsageTrackingCallback


QUIZ_BATCH_SYSTEM_PROMPT = """你是一个专业的习题出题专家。你的任务是基于给定的知识库片段，一次生成全部题目。

重要约束：
1. 所有答案必须能从原文找到依据，绝不编造
2. 同一知识点的内容不重复出题
3. 题干要转述，避免直接照抄原文
4. 选择题选项要有区分度，干扰项需看似合理但明显错误

题型规范：
- single_choice: 4个选项，1个正确
- multi_choice: 4~6个选项，2~4个正确（题干中需注明"多选"）
- short_answer: 答案30-100字，附3-5个关键词，允许多种表述
- essay: 综合性问题，附分步骤评分标准"""

QUIZ_BATCH_USER_PROMPT = """基于以下 {chunk_count} 个知识片段，生成 {total_count} 道题。

知识片段：
---
{context}
---

题型分布：{type_distribution}
难度：{difficulty}

请严格按JSON格式输出（不要包含markdown代码块之外的内容）：
```json
{{
  "questions": [
    {{
      "type": "single_choice",
      "difficulty": "medium",
      "source_chunk_index": 0,
      "question": "题目文本",
      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
      "correct_answer": "A",
      "explanation": "解析文本"
    }},
    {{
      "type": "short_answer",
      "difficulty": "medium",
      "source_chunk_index": 0,
      "question": "题目文本",
      "keywords": ["关键词1", "关键词2", "关键词3"],
      "answer_template": "标准答案",
      "explanation": "解析文本"
    }}
  ]
}}
```

source_chunk_index 表示题目来源于第几个知识片段。
请确保所有题目的答案都能在对应片段中找到依据。"""


class QuizGeneratorService:
    """题目生成服务"""

    def __init__(self):
        self.rag = RAGService()

    async def generate_quiz(
        self,
        session_id: str,
        folder_ids: Optional[list[int]] = None,
        pages: Optional[list[dict]] = None,
        question_count: int = 10,
        type_distribution: Optional[dict[str, int]] = None,
        difficulty: str = "medium",
        title: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """
        批量生成题目集

        Args:
            folder_ids: 收藏夹 ID 列表（folder 模式）
            pages: 分P 列表（pages 模式），格式 [{"bvid":"BVxxx","cid":123,"page_index":0,"page_title":"P1"}]

        Returns: (quiz_uuid, actual_count, estimated_tokens)
        """
        is_pages_mode = bool(pages)
        if not is_pages_mode and not folder_ids:
            raise ValueError("请提供 folder_ids 或 pages")

        # 默认题型分布
        if type_distribution is None:
            type_distribution = {
                "single_choice": max(2, question_count // 3),
                "multi_choice": max(1, question_count // 4),
                "short_answer": max(1, question_count // 4),
                "essay": max(1, question_count // 5),
            }
            total = sum(type_distribution.values())
            if total != question_count:
                type_distribution["single_choice"] += question_count - total

        quiz_uuid = str(uuid.uuid4())

        # 1. 创建 QuizSet 记录
        async with get_db_context() as db:
            quiz_set = QuizSet(
                quiz_uuid=quiz_uuid,
                session_id=session_id,
                title=title or f"练习 {datetime.utcnow().strftime('%m-%d %H:%M')}",
                question_count=question_count,
                type_distribution=type_distribution,
                difficulty=difficulty,
                folder_ids=folder_ids or [],
                source_type="pages" if is_pages_mode else "folder",
                source_pages=pages if is_pages_mode else None,
                status="generating",
            )
            db.add(quiz_set)
            await db.commit()

        try:
            # 2. 检索知识片段
            if is_pages_mode:
                chunks = await self._retrieve_chunks_by_pages(pages, question_count)
            else:
                bvids = await self._get_bvids_by_folder_ids(folder_ids)
                chunks = await self._retrieve_chunks(bvids, question_count)
            min_chunks = max(1, question_count // 5) if is_pages_mode else max(1, question_count // 3)
            if len(chunks) < min_chunks:
                raise ValueError(f"可用知识片段不足: {len(chunks)} < {min_chunks}")

            # 3. 批量生成（1次 LLM 调用）
            questions = await self._batch_generate(chunks, question_count, type_distribution, difficulty, session_id)

            # 4. 质量校验
            valid_questions = [q for q in questions if self._validate_question(q, chunks)]

            # 5. 保存到 DB（使用原生 SQL，因为 QuizQuestion 无 ORM session）
            await self._save_questions(quiz_uuid, valid_questions, chunks)

            # 6. 更新状态
            async with get_db_context() as db:
                qs = await db.get(QuizSet, quiz_uuid)  # quiz_uuid is not PK, need query
                result = await db.execute(
                    select(QuizSet).where(QuizSet.quiz_uuid == quiz_uuid)
                )
                qs = result.scalar_one_or_none()
                if qs:
                    qs.status = "done"
                    qs.bvid_count = len(set(q.get("bvid", "") for q in valid_questions))
                    qs.completed_at = datetime.utcnow()
                    await db.commit()

            est_tokens = sum(len(c["content"]) for c in chunks) // 3
            logger.info(f"[QUIZ] generated quiz_uuid={quiz_uuid} questions={len(valid_questions)} tokens~{est_tokens}")
            return quiz_uuid, len(valid_questions), est_tokens

        except Exception as e:
            logger.error(f"[QUIZ] generation failed quiz_uuid={quiz_uuid}: {e}")
            async with get_db_context() as db:
                result = await db.execute(
                    select(QuizSet).where(QuizSet.quiz_uuid == quiz_uuid)
                )
                qs = result.scalar_one_or_none()
                if qs:
                    qs.status = "failed"
                    qs.error_message = str(e)
                    await db.commit()
            raise

    async def _get_bvids_by_folder_ids(self, folder_ids: list[int]) -> list[str]:
        """获取指定收藏夹的 BV 列表"""
        async with get_db_context() as db:
            rows = await db.execute(
                select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id.in_(folder_ids))
            )
            bvids = []
            seen = set()
            for (bvid,) in rows.fetchall():
                if bvid not in seen:
                    seen.add(bvid)
                    bvids.append(bvid)
        return bvids

    async def _retrieve_chunks(
        self,
        bvids: list[str],
        question_count: int,
    ) -> list[dict]:
        """
        检索出题用的知识片段，多轮多样化查询确保覆盖面。
        """
        queries = [
            "概念 定义 原理 什么是",
            "方法 步骤 流程 怎么做",
            "原因 为什么 机制 背景",
            "特点 优势 区别 对比",
            "应用 场景 案例 实例",
        ]

        seen_bvids: set[str] = set()
        chunks: list[dict] = []
        target = int(question_count * 1.5)

        for query in queries:
            try:
                results = self.rag.search(query, k=5, bvids=bvids)
            except Exception as e:
                logger.warning(f"[QUIZ] search failed query={query}: {e}")
                continue

            for doc in results:
                doc_bvid = doc.metadata.get("bvid", "")
                if doc_bvid not in seen_bvids and len(doc.page_content) >= 200:
                    seen_bvids.add(doc_bvid)
                    chunks.append({
                        "bvid": doc_bvid,
                        "title": doc.metadata.get("title", ""),
                        "content": doc.page_content[:3000],
                        "chunk_index": doc.metadata.get("chunk_index"),
                    })
                    if len(chunks) >= target:
                        return chunks

        return chunks

    async def _retrieve_chunks_by_pages(
        self,
        pages: list[dict],
        question_count: int,
    ) -> list[dict]:
        """
        按指定分P检索出题用的知识片段。
        pages: [{"bvid": "BVxxx", "cid": 123, "page_index": 0, "page_title": "P1"}, ...]
        """
        queries = [
            "概念 定义 原理 什么是",
            "方法 步骤 流程 怎么做",
            "原因 为什么 机制 背景",
            "特点 优势 区别 对比",
            "应用 场景 案例 实例",
        ]

        seen_chunk_ids: set[str] = set()
        chunks: list[dict] = []
        target = int(question_count * 1.5)

        workspace_pages = [
            {"bvid": p["bvid"], "page_index": p["page_index"]}
            for p in pages
        ]

        for query in queries:
            try:
                results = self.rag.search(query, k=5, workspace_pages=workspace_pages)
            except Exception as e:
                logger.warning(f"[QUIZ] pages search failed query={query}: {e}")
                continue

            for doc in results:
                chunk_id = doc.metadata.get("chunk_id", "")
                if not chunk_id:
                    # Fallback: construct unique key from metadata
                    bvid_fb = doc.metadata.get("bvid", "")
                    pi_fb = doc.metadata.get("page_index", 0)
                    ci_fb = doc.metadata.get("chunk_index", 0)
                    chunk_id = f"{bvid_fb}:{pi_fb}:{ci_fb}"
                if chunk_id in seen_chunk_ids or len(doc.page_content) < 100:
                    continue
                seen_chunk_ids.add(chunk_id)
                bvid = doc.metadata.get("bvid", "")
                page_idx = doc.metadata.get("page_index", 0)
                # Match back to the page title
                page_title = ""
                for p in pages:
                    if p["bvid"] == bvid and p["page_index"] == page_idx:
                        page_title = p.get("page_title", "")
                        break
                chunks.append({
                    "bvid": bvid,
                    "title": doc.metadata.get("title", ""),
                    "page_index": page_idx,
                    "page_title": page_title or doc.metadata.get("page_title", ""),
                    "content": doc.page_content[:3000],
                    "chunk_index": doc.metadata.get("chunk_index"),
                })
                if len(chunks) >= target:
                    return chunks

        return chunks

    async def _batch_generate(
        self,
        chunks: list[dict],
        total_count: int,
        type_distribution: dict,
        difficulty: str,
        session_id: str = "",
    ) -> list[dict]:
        """批量生成所有题目（1次 LLM 调用）"""
        context_parts = []
        for i, c in enumerate(chunks):
            context_parts.append(f"【片段{i}】来源: {c['title']}\n{c['content']}")
        context = "\n\n---\n\n".join(context_parts)

        type_desc = "、".join(
            f"{v}道{qtype}" for qtype, v in type_distribution.items() if v > 0
        )

        prompt = QUIZ_BATCH_USER_PROMPT.format(
            chunk_count=len(chunks),
            total_count=total_count,
            context=context,
            type_distribution=type_desc,
            difficulty=difficulty,
        )

        llm = self._get_llm(temperature=0.7)

        # Attach usage tracking callback
        provider = "openai"
        base_url = settings.openai_base_url or ""
        if "deepseek" in base_url:
            provider = "deepseek"
        elif "anthropic" in base_url:
            provider = "anthropic"
        writer = get_buffered_usage_writer()
        tracker = UsageTrackingCallback(
            session_id=session_id,
            provider=provider,
            model=settings.llm_model,
            writer=writer,
        )
        llm.callbacks = [tracker]

        response = await llm.ainvoke([
            {"role": "system", "content": QUIZ_BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        text = response.content.strip()

        # 解析 JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text)
        questions = data.get("questions", [])

        # 注入来源信息
        for q in questions:
            chunk_idx = q.get("source_chunk_index", 0)
            if chunk_idx < len(chunks):
                q["bvid"] = chunks[chunk_idx]["bvid"]
                q["source_segment"] = chunks[chunk_idx]["content"][:500]
            q["question_uuid"] = str(uuid.uuid4())

        logger.info(f"[QUIZ] batch generated {len(questions)} questions")
        return questions

    @staticmethod
    def _get_llm(temperature: float = 0.7) -> ChatOpenAI:
        """获取 LLM 实例（使用系统默认 Key）"""
        api_key = settings.openai_api_key
        base_url = settings.openai_base_url
        model = settings.llm_model

        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
        )

    def _validate_question(self, q: dict, chunks: list[dict]) -> bool:
        """校验单道题目的质量"""
        # 1. 基本字段检查
        if not q.get("question") or not q.get("correct_answer"):
            return False

        # 2. 答案溯源
        chunk_idx = q.get("source_chunk_index", 0)
        if chunk_idx < len(chunks):
            source = chunks[chunk_idx]["content"].lower()
            answer = q.get("correct_answer", "")
            if isinstance(answer, list):
                answer_text = " ".join(str(a) for a in answer)
            else:
                answer_text = str(answer)

            if len(answer_text) > 2 and answer_text.lower() not in source:
                core_words = [w for w in answer_text.lower().split() if len(w) > 1]
                if core_words and not any(w in source for w in core_words):
                    logger.warning(f"[QUIZ] answer not traced to source: {answer_text[:50]}")
                    return False

        # 3. 选择题选项检查
        qtype = q.get("type", "")
        if qtype in ("single_choice", "multi_choice"):
            options = q.get("options", [])
            if len(options) < 4:
                return False
        if qtype == "multi_choice":
            correct = q.get("correct_answer", [])
            if isinstance(correct, list) and len(correct) < 2:
                return False

        # 4. 简答题关键词检查
        if qtype == "short_answer":
            keywords = q.get("keywords", [])
            if not keywords:
                return False

        return True

    async def _save_questions(
        self, quiz_uuid: str, questions: list[dict], chunks: list[dict]
    ):
        """批量保存题目（原生 SQL）"""
        async with get_db_context() as db:
            from sqlalchemy import text
            for q in questions:
                await db.execute(
                    text(
                        """INSERT INTO quiz_questions
                           (quiz_uuid, question_uuid, bvid, chunk_id, source_segment,
                            question_type, difficulty, question_text, options,
                            correct_answer, explanation, keywords, answer_template,
                            scoring_rubric, model_answer, is_valid)
                           VALUES
                           (:quiz_uuid, :question_uuid, :bvid, :chunk_id, :source_segment,
                            :question_type, :difficulty, :question_text, :options,
                            :correct_answer, :explanation, :keywords, :answer_template,
                            :scoring_rubric, :model_answer, :is_valid)"""
                    ),
                    {
                        "quiz_uuid": quiz_uuid,
                        "question_uuid": q["question_uuid"],
                        "bvid": q.get("bvid"),
                        "chunk_id": str(q.get("source_chunk_index", "")),
                        "source_segment": q.get("source_segment"),
                        "question_type": q.get("type"),
                        "difficulty": q.get("difficulty", "medium"),
                        "question_text": q.get("question"),
                        "options": json.dumps(q.get("options")) if q.get("options") else None,
                        "correct_answer": json.dumps(q.get("correct_answer")),
                        "explanation": q.get("explanation"),
                        "keywords": json.dumps(q.get("keywords")) if q.get("keywords") else None,
                        "answer_template": q.get("answer_template"),
                        "scoring_rubric": json.dumps(q.get("scoring_rubric")) if q.get("scoring_rubric") else None,
                        "model_answer": q.get("model_answer"),
                        "is_valid": True,
                    },
                )
            await db.commit()


async def get_quiz_set(quiz_uuid: str) -> Optional[QuizSet]:
    """获取题目集"""
    async with get_db_context() as db:
        result = await db.execute(
            select(QuizSet).where(QuizSet.quiz_uuid == quiz_uuid)
        )
        return result.scalar_one_or_none()


async def get_quiz_questions(quiz_uuid: str) -> list[dict]:
    """获取题目集的所有题目（不含答案的摘要）"""
    async with get_db_context() as db:
        from sqlalchemy import text
        result = await db.execute(
            text(
                """SELECT question_uuid, question_type, difficulty, question_text, options
                   FROM quiz_questions
                   WHERE quiz_uuid = :quiz_uuid AND is_valid = 1"""
            ),
            {"quiz_uuid": quiz_uuid},
        )
        return [dict(row._mapping) for row in result.fetchall()]


async def get_quiz_questions_full(quiz_uuid: str) -> list[dict]:
    """获取题目集的所有题目（含答案，用于批改）"""
    async with get_db_context() as db:
        from sqlalchemy import text
        result = await db.execute(
            text(
                """SELECT * FROM quiz_questions
                   WHERE quiz_uuid = :quiz_uuid AND is_valid = 1"""
            ),
            {"quiz_uuid": quiz_uuid},
        )
        return [dict(row._mapping) for row in result.fetchall()]
