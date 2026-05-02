"""
Quiz 题目训练系统路由 — 题目生成、提交批改、历史、错题、导出。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from loguru import logger

from app.services.quiz_generator import QuizGeneratorService, get_quiz_set, get_quiz_questions, get_quiz_questions_full
from app.services.quiz_grader import QuizGraderService
from app.services.quiz_export import QuizDataExportService
from app.database import get_db_context

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate")
async def generate_quiz(
    session_id: str = Query(..., description="用户 session"),
    folder_ids: Optional[str] = Query(None, description="逗号分隔的收藏夹ID"),
    pages: Optional[list[dict]] = Body(None, description="分P列表 [{\"bvid\":\"BVxxx\",\"cid\":123,\"page_index\":0,\"page_title\":\"P1\"}]"),
    question_count: int = Query(10, ge=1, le=50),
    difficulty: str = Query("medium", pattern="^(easy|medium|hard)$"),
    title: Optional[str] = Query(None),
):
    """生成一套练习题（支持按收藏夹或按分P出题）"""
    fids = [int(x.strip()) for x in folder_ids.split(",") if x.strip()] if folder_ids else []
    if not fids and not pages:
        raise HTTPException(400, "请提供 folder_ids 或 pages")

    service = QuizGeneratorService()
    try:
        quiz_uuid, count, est_tokens = await service.generate_quiz(
            session_id=session_id,
            folder_ids=fids if fids else None,
            pages=pages,
            question_count=question_count,
            difficulty=difficulty,
            title=title,
        )
        return {
            "quiz_uuid": quiz_uuid,
            "question_count": count,
            "estimated_cost_tokens": est_tokens,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.get("/{quiz_uuid}")
async def get_quiz(quiz_uuid: str, include_answers: bool = Query(False)):
    """获取题目集（不含答案用于答题，include_answers=true 含答案用于下载/回看）"""
    quiz_set = await get_quiz_set(quiz_uuid)
    if not quiz_set:
        raise HTTPException(404, "题目集不存在")

    questions = await (get_quiz_questions_full(quiz_uuid) if include_answers else get_quiz_questions(quiz_uuid))

    import json as _json
    return {
        "quiz_uuid": quiz_set.quiz_uuid,
        "title": quiz_set.title,
        "status": quiz_set.status,
        "question_count": quiz_set.question_count,
        "type_distribution": quiz_set.type_distribution,
        "difficulty": quiz_set.difficulty,
        "total_score": quiz_set.total_score,
        "passing_score": quiz_set.passing_score,
        "source_type": getattr(quiz_set, "source_type", "folder") or "folder",
        "source_pages": getattr(quiz_set, "source_pages", None),
        "created_at": str(quiz_set.created_at) if quiz_set.created_at else "",
        "questions": [
            {
                "question_uuid": q["question_uuid"],
                "question_type": q["question_type"],
                "difficulty": q["difficulty"],
                "question_text": q["question_text"],
                "options": _json.loads(q["options"]) if isinstance(q.get("options"), str) else q.get("options"),
                **(
                    {
                        "correct_answer": _json.loads(q["correct_answer"]) if isinstance(q.get("correct_answer"), str) else q.get("correct_answer"),
                        "explanation": q.get("explanation"),
                        "keywords": _json.loads(q["keywords"]) if isinstance(q.get("keywords"), str) else q.get("keywords"),
                    }
                    if include_answers else {}
                ),
            }
            for q in questions
        ],
    }


@router.post("/submit")
async def submit_quiz(body: dict):
    """提交答案并即时批改"""
    quiz_uuid = body.get("quiz_uuid")
    session_id = body.get("session_id")
    answers = body.get("answers", [])
    time_spent = body.get("time_spent_seconds")

    if not quiz_uuid or not session_id:
        raise HTTPException(400, "缺少 quiz_uuid 或 session_id")

    if not answers:
        raise HTTPException(400, "缺少 answers")

    service = QuizGraderService()
    try:
        result = await service.submit_and_grade(
            quiz_uuid=quiz_uuid,
            session_id=session_id,
            answers=answers,
            time_spent_seconds=time_spent,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[QUIZ] submit failed: {e}")
        raise HTTPException(500, f"批改失败: {e}")


@router.get("/history")
async def get_history(
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """获取题目历史（所有已生成的 quiz，含答题状态）"""
    async with get_db_context() as db:
        from sqlalchemy import text

        # 查询总数（以 quiz_sets 为主表）
        count_result = await db.execute(
            text(
                """SELECT COUNT(*) FROM quiz_sets
                   WHERE session_id = :session_id AND status IN ('done', 'failed')"""
            ),
            {"session_id": session_id},
        )
        total = count_result.scalar()

        # 查询分页数据：quiz_sets LEFT JOIN quiz_submissions
        offset = (page - 1) * page_size
        result = await db.execute(
            text(
                """SELECT qs.quiz_uuid, qs.title, qs.question_count,
                          qs.difficulty, qs.status, qs.source_type,
                          qs.created_at,
                          qsub.submission_uuid, qsub.total_score,
                          qsub.is_passed, qsub.correct_count,
                          qsub.total_question_count, qsub.time_spent_seconds,
                          qsub.submitted_at
                   FROM quiz_sets qs
                   LEFT JOIN quiz_submissions qsub
                     ON qsub.quiz_uuid = qs.quiz_uuid AND qsub.session_id = :session_id
                   WHERE qs.session_id = :session_id
                     AND qs.status IN ('done', 'failed')
                   ORDER BY qs.created_at DESC
                   LIMIT :limit OFFSET :offset"""
            ),
            {"session_id": session_id, "limit": page_size, "offset": offset},
        )
        submissions = []
        for row in result.fetchall():
            d = dict(row._mapping)
            submissions.append({
                "submission_uuid": d["submission_uuid"],
                "quiz_uuid": d["quiz_uuid"],
                "title": d["title"],
                "status": d["status"],
                "question_count": d["question_count"],
                "difficulty": d["difficulty"],
                "source_type": d["source_type"],
                "score": d["total_score"],
                "passed": bool(d["is_passed"]) if d["is_passed"] is not None else None,
                "correct_count": d["correct_count"],
                "total_question_count": d["total_question_count"],
                "time_spent_seconds": d["time_spent_seconds"],
                "submitted_at": d["submitted_at"],
                "created_at": str(d["created_at"]) if d["created_at"] else "",
            })

        return {
            "submissions": submissions,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < total,
        }


@router.get("/wrong-answers")
async def get_wrong_answers(
    session_id: str = Query(...),
    folder_ids: Optional[str] = Query(None),
):
    """获取错题本"""
    async with get_db_context() as db:
        from sqlalchemy import text

        sql = """
            SELECT qq.question_uuid, qq.quiz_uuid, qq.question_type,
                   qq.question_text, qq.options,
                   qa.user_answer, qa.correct_answer_snapshot,
                   qq.explanation,
                   COUNT(qa.id) as times_wrong,
                   MAX(qa.submitted_at) as last_attempt_at
            FROM quiz_answers qa
            JOIN quiz_submissions qsub ON qsub.submission_uuid = qa.submission_uuid
            JOIN quiz_questions qq ON qq.question_uuid = qa.question_uuid
            WHERE qsub.session_id = :session_id AND qa.is_correct = 0
        """

        params = {"session_id": session_id}
        if folder_ids:
            sql += " AND qsub.quiz_uuid IN (SELECT quiz_uuid FROM quiz_sets WHERE session_id = :session_id)"
            # Filter by folder_ids via quiz_sets
            fids = [int(x.strip()) for x in folder_ids.split(",") if x.strip()]
            # Build dynamic filter for folder_ids (JSON array check)
            folder_conditions = []
            for i, fid in enumerate(fids):
                param_name = f"fid_{i}"
                folder_conditions.append(f"qs.folder_ids LIKE :{param_name}")
                params[param_name] = f'%{fid}%'
            if folder_conditions:
                sql += " AND (" + " OR ".join(folder_conditions) + ")"
                sql = sql.replace(
                    "FROM quiz_answers qa",
                    "FROM quiz_answers qa"
                )
                # Need to join quiz_sets for folder filtering
                sql = """
                    SELECT qq.question_uuid, qq.quiz_uuid, qq.question_type,
                           qq.question_text, qq.options,
                           qa.user_answer, qa.correct_answer_snapshot,
                           qq.explanation,
                           COUNT(qa.id) as times_wrong,
                           MAX(qa.submitted_at) as last_attempt_at
                    FROM quiz_answers qa
                    JOIN quiz_submissions qsub ON qsub.submission_uuid = qa.submission_uuid
                    JOIN quiz_questions qq ON qq.question_uuid = qa.question_uuid
                    JOIN quiz_sets qs ON qs.quiz_uuid = qsub.quiz_uuid
                    WHERE qsub.session_id = :session_id AND qa.is_correct = 0
                """ + (" AND (" + " OR ".join(folder_conditions) + ")")

        sql += " GROUP BY qq.question_uuid ORDER BY last_attempt_at DESC"

        result = await db.execute(text(sql), params)
        wrong_answers = []
        import json as _json
        for row in result.fetchall():
            d = dict(row._mapping)
            user_answer = _json.loads(d["user_answer"]) if d["user_answer"] else d["user_answer"]
            correct_answer = _json.loads(d["correct_answer_snapshot"]) if d["correct_answer_snapshot"] else d["correct_answer_snapshot"]
            options_data = _json.loads(d["options"]) if isinstance(d.get("options"), str) else d.get("options")

            wrong_answers.append({
                "question_uuid": d["question_uuid"],
                "quiz_uuid": d["quiz_uuid"],
                "question_type": d["question_type"],
                "question_text": d["question_text"],
                "options": options_data,
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "explanation": d["explanation"],
                "times_wrong": d["times_wrong"],
                "last_attempt_at": d["last_attempt_at"],
            })

        return {"wrong_answers": wrong_answers, "total": len(wrong_answers)}


@router.get("/export")
async def export_quiz_data(
    session_id: str = Query(...),
    format: str = Query("jsonl", pattern="^(jsonl|csv|sft)$"),
    folder_ids: Optional[str] = Query(None, description="逗号分隔的收藏夹ID"),
):
    """导出答题训练数据（流式响应）"""
    fids = [int(x.strip()) for x in folder_ids.split(",") if x.strip()] if folder_ids else None

    service = QuizDataExportService()

    async def generate():
        async for row in service.export_submissions(session_id, fids, format):
            yield row

    content_type = {
        "jsonl": "application/jsonl",
        "csv": "text/csv",
        "sft": "application/jsonl",
    }[format]

    filename = f"quiz_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

    return StreamingResponse(
        generate(),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache",
        },
    )
