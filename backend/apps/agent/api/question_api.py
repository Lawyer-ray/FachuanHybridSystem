"""Agent 提问 API —— 模型向律师提问的回答提交与待答列表。

端点前缀：``/api/v1/agent``（提问子域）。提问不是审批：超时不阻断，
模型按假设继续。
"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import QuestionAnswerIn
from ..services.question import get_question_by_id, list_pending_questions_for_user, submit_answer
from ._helpers import _current_user

router = Router(tags=["Agent 提问"], auth=JWTOrSessionAuth())


def _may_answer(user: Any, record: Any) -> bool:
    """提问归属判定：会话所有者或超级用户（与审批同口径）。"""
    if user is not None and getattr(user, "is_superuser", False):
        return True
    owner_id = getattr(record.session, "user_id", None) if record.session is not None else None
    if owner_id is None:
        owner_id = getattr(record, "user_id", None)
    return user is not None and owner_id is not None and int(owner_id) == int(user.pk)


@router.post("/question/{question_id}/answer")
async def submit_question_answer(  # pragma: no cover
    request: Any,
    question_id: str,
    payload: QuestionAnswerIn,
) -> dict[str, Any]:
    """前端提交提问回答（仅会话所有者或超级用户）。

    ``success=False`` 不一定是错误：等待方可能已超时（律师过了 5 分钟才点
    提交）。此时答案仍被记录，但模型已经按假设继续了——前端应提示「回答已
    记录，但本轮已继续」，而不是当成失败重试。
    """
    user = _current_user(request)
    record = await get_question_by_id(question_id)
    if record is None:
        return {"success": False, "error": "提问不存在"}
    if not _may_answer(user, record):
        return {"success": False, "error": "无权回答该提问"}

    found = await submit_answer(
        question_id=question_id,
        answers=[item.model_dump() for item in payload.answers],
        skipped=payload.skipped,
    )
    return {
        "success": found,
        "accepted": True,
        "note": "" if found else "回答已记录，但本轮对话已按超时继续",
    }


@router.get("/questions/pending", response=list[dict[str, Any]])
async def list_pending_questions(request: Any) -> list[dict[str, Any]]:  # pragma: no cover
    """当前律师待回答的提问（重开会话时补拉，避免错过）。"""
    user = _current_user(request)
    if user is None:
        return []
    rows = await list_pending_questions_for_user(user.pk, limit=20)
    return [
        {
            "question_id": str(row.question_id),
            "session_id": str(row.session.session_id) if row.session else "",
            "questions": row.questions,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
