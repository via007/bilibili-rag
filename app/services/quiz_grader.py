"""
Quiz 自动批改服务 — 客观题精确批改，简答题关键词匹配，主观题 LLM 评分。
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from langchain_openai import ChatOpenAI

from app.config import settings
from app.database import get_db_context
from app.services.quiz_generator import get_quiz_set, get_quiz_questions_full


ESSAY_GRADING_SYSTEM = "你是一个严格的评分老师。根据评分标准对答案进行客观评分。"

ESSAY_GRADING_PROMPT = """请根据评分标准对学生的答案进行评分。

【题目】
{question_text}

【评分标准】
{scoring_rubric}

【参考答案】
{model_answer}

【学生答案】
{user_answer}

请按JSON格式输出：
```json
{{
  "total_score": 总分,
  "max_score": 满分,
  "step_scores": [
    {{"step": "第一步名称", "max_points": 2, "score": 1, "reason": "评分理由"}}
  ],
  "overall_feedback": "总体评价",
  "strengths": ["优点"],
  "weaknesses": ["不足"]
}}
```"""


class QuizGraderService:
    """题目批改服务"""

    async def submit_and_grade(
        self,
        quiz_uuid: str,
        session_id: str,
        answers: list[dict],
        time_spent_seconds: Optional[int] = None,
    ) -> dict:
        """提交并批改"""
        submission_uuid = str(uuid.uuid4())

        # 1. 获取题目集和题目
        quiz_set = await get_quiz_set(quiz_uuid)
        if not quiz_set:
            raise ValueError("题目集不存在")

        questions = await get_quiz_questions_full(quiz_uuid)
        question_map = {q["question_uuid"]: q for q in questions}

        total_question_count = len(questions)
        passing_score = quiz_set.passing_score

        # 2. 创建提交记录
        await self._create_submission(
            submission_uuid, quiz_uuid, session_id, total_question_count, passing_score, time_spent_seconds
        )

        # 3. 逐题批改
        graded_results = []
        total_score = 0
        correct_count = 0

        for answer_item in answers:
            q_uuid = answer_item["question_uuid"]
            user_answer = answer_item["answer"]
            question = question_map.get(q_uuid)
            if not question:
                continue

            correct_answer = json.loads(question["correct_answer"]) if isinstance(question["correct_answer"], str) else question["correct_answer"]
            qtype = question["question_type"]
            grading_note = None

            if qtype == "single_choice":
                result = self._grade_single_choice(user_answer, correct_answer)
            elif qtype == "multi_choice":
                result = self._grade_multi_choice(user_answer, correct_answer)
            elif qtype == "short_answer":
                keywords = json.loads(question["keywords"]) if isinstance(question.get("keywords"), str) else (question.get("keywords") or [])
                result = self._grade_short_answer(user_answer, str(correct_answer), keywords)
                grading_note = "关键词自动评分，仅供参考"
            elif qtype == "essay":
                rubric = json.loads(question["scoring_rubric"]) if isinstance(question.get("scoring_rubric"), str) else (question.get("scoring_rubric") or [])
                try:
                    result = await self._grade_essay(
                        question["question_text"], str(user_answer),
                        rubric, question.get("model_answer"),
                    )
                    grading_note = "AI辅助评分，可人工修改"
                except Exception as e:
                    logger.warning(f"[GRADER] essay grading failed: {e}")
                    result = {"auto_score": 5, "grading_detail": {"type": "default"}, "grading_note": "LLM评分失败，默认给5分"}
                    grading_note = "LLM评分失败，默认给5分"
            else:
                result = {"auto_score": 0, "grading_detail": {"type": "unknown"}}

            score = result.get("auto_score", 0)
            is_correct = result.get("is_correct", False)

            # 4. 保存答案记录
            await self._save_answer(
                submission_uuid, q_uuid, qtype, user_answer,
                correct_answer, result, grading_note,
            )

            total_score += score
            if is_correct:
                correct_count += 1

            graded_results.append({
                "question_uuid": q_uuid,
                "is_correct": is_correct,
                "auto_score": score,
                "correct_answer": correct_answer,
                "grading_note": grading_note or result.get("grading_note"),
            })

        # 5. 更新提交记录
        passed = total_score >= passing_score
        await self._update_submission(submission_uuid, total_score, correct_count, passed)

        return {
            "submission_uuid": submission_uuid,
            "score": total_score,
            "passed": passed,
            "correct_count": correct_count,
            "total_count": total_question_count,
            "results": graded_results,
        }

    def _grade_single_choice(self, user_answer, correct_answer) -> dict:
        """单选题：字符串精确匹配"""
        ua = str(user_answer).strip().upper()
        ca = str(correct_answer).strip().upper()
        ok = ua == ca
        return {"is_correct": ok, "auto_score": 10 if ok else 0}

    def _grade_multi_choice(self, user_answer, correct_answer) -> dict:
        """多选题：部分给分"""
        user_set = set(str(a).strip().upper() for a in user_answer)
        correct_set = set(str(a).strip().upper() for a in correct_answer)

        correct_picks = len(user_set & correct_set)
        wrong_picks = len(user_set - correct_set)
        points_per = round(10 / len(correct_set), 2) if correct_set else 0
        score = max(0, min(10, round(correct_picks * points_per - wrong_picks * 1)))

        return {
            "is_correct": user_set == correct_set,
            "auto_score": score,
            "grading_detail": {
                "type": "partial_credit",
                "user_set": list(user_set),
                "correct_set": list(correct_set),
                "correct_picks": correct_picks,
                "wrong_picks": wrong_picks,
            },
        }

    def _grade_short_answer(self, user_answer: str, correct_answer: str, keywords: list) -> dict:
        """简答题：关键词匹配"""
        user_lower = str(user_answer).lower()
        matched = [kw for kw in keywords if kw.lower() in user_lower]
        match_rate = len(matched) / len(keywords) if keywords else 0
        score = round(match_rate * 8)

        return {
            "is_correct": match_rate >= 0.5,
            "auto_score": score,
            "matched_keywords": matched,
            "keyword_match_rate": round(match_rate, 3),
            "grading_detail": {
                "type": "keyword_match",
                "total_keywords": len(keywords),
                "matched_count": len(matched),
                "ratio": round(match_rate, 3),
            },
            "grading_note": "关键词自动评分，仅供参考",
        }

    async def _grade_essay(
        self,
        question_text: str,
        user_answer: str,
        scoring_rubric: list,
        model_answer: Optional[str],
    ) -> dict:
        """主观题：LLM 评分"""
        total_max = sum(r.get("points", 0) for r in scoring_rubric)

        rubric_text = "\n".join(
            f"- {r.get('step', '步骤')}（{r.get('points', 0)}分）：关键词 {', '.join(r.get('keywords', []))}"
            for r in scoring_rubric
        )

        prompt = ESSAY_GRADING_PROMPT.format(
            question_text=question_text,
            scoring_rubric=rubric_text,
            model_answer=model_answer or "暂无参考答案",
            user_answer=user_answer,
        )

        llm = self._get_llm()
        response = await llm.ainvoke([
            {"role": "system", "content": ESSAY_GRADING_SYSTEM},
            {"role": "user", "content": prompt},
        ])

        text = response.content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        data = json.loads(text)

        return {
            "auto_score": data.get("total_score", 0),
            "max_score": total_max,
            "grading_detail": {
                "type": "llm_essay_grading",
                "step_scores": data.get("step_scores", []),
                "feedback": data.get("overall_feedback", ""),
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
            },
            "grading_note": "AI辅助评分，可人工修改",
        }

    @staticmethod
    def _get_llm() -> ChatOpenAI:
        """获取 LLM 实例（用于主观题评分，低温度确保一致性）"""
        api_key = settings.openai_api_key
        base_url = settings.openai_base_url
        model = settings.llm_model

        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
        )

    async def _create_submission(
        self,
        submission_uuid: str,
        quiz_uuid: str,
        session_id: str,
        total_question_count: int,
        passing_score: int,
        time_spent_seconds: Optional[int],
    ):
        async with get_db_context() as db:
            from sqlalchemy import text
            await db.execute(
                text(
                    """INSERT INTO quiz_submissions
                       (submission_uuid, quiz_uuid, session_id, total_question_count,
                        passing_score, is_complete, time_spent_seconds, started_at, submitted_at)
                       VALUES
                       (:submission_uuid, :quiz_uuid, :session_id, :total_question_count,
                        :passing_score, :is_complete, :time_spent_seconds, :started_at, :submitted_at)"""
                ),
                {
                    "submission_uuid": submission_uuid,
                    "quiz_uuid": quiz_uuid,
                    "session_id": session_id,
                    "total_question_count": total_question_count,
                    "passing_score": passing_score,
                    "is_complete": False,
                    "time_spent_seconds": time_spent_seconds,
                    "started_at": datetime.utcnow().isoformat(),
                    "submitted_at": datetime.utcnow().isoformat(),
                },
            )
            await db.commit()

    async def _save_answer(
        self,
        submission_uuid: str,
        question_uuid: str,
        question_type: str,
        user_answer,
        correct_answer,
        result: dict,
        grading_note: Optional[str],
    ):
        async with get_db_context() as db:
            from sqlalchemy import text
            is_correct_int = 1 if result.get("is_correct") else 0
            matched_keywords = json.dumps(result.get("matched_keywords")) if result.get("matched_keywords") else None
            grading_detail = json.dumps(result.get("grading_detail")) if result.get("grading_detail") else None

            await db.execute(
                text(
                    """INSERT INTO quiz_answers
                       (submission_uuid, question_uuid, question_type, user_answer,
                        user_answer_text, is_correct, auto_score, correct_answer_snapshot,
                        matched_keywords, keyword_match_rate, grading_detail, submitted_at, graded_at)
                       VALUES
                       (:submission_uuid, :question_uuid, :question_type, :user_answer,
                        :user_answer_text, :is_correct, :auto_score, :correct_answer_snapshot,
                        :matched_keywords, :keyword_match_rate, :grading_detail, :submitted_at, :graded_at)"""
                ),
                {
                    "submission_uuid": submission_uuid,
                    "question_uuid": question_uuid,
                    "question_type": question_type,
                    "user_answer": json.dumps(user_answer) if isinstance(user_answer, (list, dict)) else str(user_answer),
                    "user_answer_text": str(user_answer) if not isinstance(user_answer, str) else user_answer,
                    "is_correct": is_correct_int,
                    "auto_score": result.get("auto_score", 0),
                    "correct_answer_snapshot": json.dumps(correct_answer) if isinstance(correct_answer, (list, dict)) else str(correct_answer),
                    "matched_keywords": matched_keywords,
                    "keyword_match_rate": result.get("keyword_match_rate"),
                    "grading_detail": grading_detail,
                    "submitted_at": datetime.utcnow().isoformat(),
                    "graded_at": datetime.utcnow().isoformat(),
                },
            )
            await db.commit()

    async def _update_submission(
        self,
        submission_uuid: str,
        total_score: int,
        correct_count: int,
        passed: bool,
    ):
        async with get_db_context() as db:
            from sqlalchemy import text
            await db.execute(
                text(
                    """UPDATE quiz_submissions
                       SET total_score = :total_score, auto_score = :total_score,
                           correct_count = :correct_count, is_complete = 1,
                           is_passed = :is_passed, graded_at = :graded_at
                       WHERE submission_uuid = :submission_uuid"""
                ),
                {
                    "submission_uuid": submission_uuid,
                    "total_score": total_score,
                    "correct_count": correct_count,
                    "is_passed": 1 if passed else 0,
                    "graded_at": datetime.utcnow().isoformat(),
                },
            )
            await db.commit()
