"""
Quiz 训练数据导出服务 — 支持 JSONL / CSV / SFT 三种格式。
"""
import csv
import io
import json
from typing import AsyncGenerator, Optional

from loguru import logger

from app.database import get_db_context


class QuizDataExportService:
    """训练数据导出服务"""

    async def export_submissions(
        self,
        session_id: str,
        folder_ids: Optional[list[int]] = None,
        format: str = "jsonl",
    ) -> AsyncGenerator[str, None]:
        """导出用户的答题数据

        Args:
            session_id: 用户会话
            folder_ids: 限定收藏夹范围（None 表示全部）
            format: 导出格式 (jsonl / csv / sft)

        Yields:
            格式化后的行数据
        """
        if format == "jsonl":
            async for row in self._export_jsonl(session_id, folder_ids):
                yield row
        elif format == "csv":
            async for row in self._export_csv(session_id, folder_ids):
                yield row
        elif format == "sft":
            async for row in self._export_sft(session_id, folder_ids):
                yield row
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def _export_jsonl(
        self, session_id: str, folder_ids: Optional[list[int]]
    ) -> AsyncGenerator[str, None]:
        """JSONL 格式导出"""
        async for record in self._iter_records(session_id, folder_ids):
            yield json.dumps(record, ensure_ascii=False) + "\n"

    async def _export_csv(
        self, session_id: str, folder_ids: Optional[list[int]]
    ) -> AsyncGenerator[str, None]:
        """CSV 格式导出"""
        fieldnames = [
            "question", "type", "difficulty", "correct_answer",
            "user_answer", "is_correct", "explanation",
            "context", "bvid", "quiz_uuid", "submission_uuid", "timestamp",
        ]

        header_written = False
        async for record in self._iter_records(session_id, folder_ids):
            if not header_written:
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                yield output.getvalue()
                header_written = True

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            # 展平复杂字段
            row = {k: record.get(k, "") for k in fieldnames}
            for k in ("correct_answer", "user_answer"):
                if isinstance(row.get(k), list):
                    row[k] = ", ".join(str(x) for x in row[k])
            writer.writerow(row)
            yield output.getvalue()

    async def _export_sft(
        self, session_id: str, folder_ids: Optional[list[int]]
    ) -> AsyncGenerator[str, None]:
        """SFT 格式导出（用于监督微调）"""
        async for record in self._iter_records(session_id, folder_ids):
            qtype = record.get("type", "")
            if qtype in ("single_choice", "multi_choice"):
                options = record.get("options") or []
                options_text = "\n".join(str(o) for o in options)
                user_content = f"{record['question']}\n{options_text}"
            else:
                user_content = record["question"]

            answer = record.get("correct_answer", "")
            if isinstance(answer, list):
                answer = ", ".join(str(a) for a in answer)

            sft_record = {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": str(answer)},
                ],
                "metadata": {
                    "type": record.get("type"),
                    "difficulty": record.get("difficulty"),
                    "bvid": record.get("bvid"),
                },
            }

            yield json.dumps(sft_record, ensure_ascii=False) + "\n"

    async def _iter_records(
        self, session_id: str, folder_ids: Optional[list[int]]
    ) -> AsyncGenerator[dict, None]:
        """迭代所有可导出的记录"""
        async with get_db_context() as db:
            from sqlalchemy import text

            sql = """
                SELECT
                    qs.quiz_uuid, qs.folder_ids,
                    qq.question_uuid, qq.question_type, qq.difficulty,
                    qq.question_text, qq.options, qq.explanation,
                    qq.source_segment, qq.bvid,
                    qa.user_answer, qa.user_answer_text, qa.is_correct,
                    qa.correct_answer_snapshot,
                    qsub.submission_uuid, qsub.submitted_at
                FROM quiz_answers qa
                JOIN quiz_submissions qsub ON qsub.submission_uuid = qa.submission_uuid
                JOIN quiz_questions qq ON qq.question_uuid = qa.question_uuid
                JOIN quiz_sets qs ON qs.quiz_uuid = qsub.quiz_uuid
                WHERE qsub.session_id = :session_id
                ORDER BY qsub.submitted_at DESC
            """
            result = await db.execute(text(sql), {"session_id": session_id})
            rows = result.fetchall()

            for row in rows:
                row_dict = dict(row._mapping)

                # 过滤 folder_ids
                if folder_ids:
                    quiz_folder_ids = json.loads(row_dict["folder_ids"]) if row_dict["folder_ids"] else []
                    if not any(fid in folder_ids for fid in quiz_folder_ids):
                        continue

                user_answer = json.loads(row_dict["user_answer"]) if row_dict["user_answer"] else row_dict["user_answer_text"]
                correct_answer = json.loads(row_dict["correct_answer_snapshot"]) if row_dict["correct_answer_snapshot"] else row_dict["correct_answer_snapshot"]
                options_data = json.loads(row_dict["options"]) if row_dict["options"] else None

                yield {
                    "question": row_dict["question_text"],
                    "type": row_dict["question_type"],
                    "difficulty": row_dict["difficulty"],
                    "options": options_data,
                    "correct_answer": correct_answer,
                    "user_answer": user_answer,
                    "is_correct": bool(row_dict["is_correct"]),
                    "explanation": row_dict["explanation"],
                    "context": row_dict["source_segment"][:500] if row_dict["source_segment"] else None,
                    "bvid": row_dict["bvid"],
                    "folder_id": row_dict["folder_ids"],
                    "quiz_uuid": row_dict["quiz_uuid"],
                    "submission_uuid": row_dict["submission_uuid"],
                    "timestamp": row_dict["submitted_at"],
                }
