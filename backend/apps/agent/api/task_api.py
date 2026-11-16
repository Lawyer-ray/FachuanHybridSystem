"""Agent 任务式（后台）API —— 提交 / 查询 / 取消后台任务。

端点前缀：``/api/v1/agent``（任务子域）。任务式运行没有 SSE 连接，
高危工具走离线审批（见 ``GET /approvals/pending``）。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentSession
from ..schemas import TaskIn, TaskOut
from ..services.session_service import create_session as create_session_record
from ..services.session_service import get_session as get_session_record
from ..services.task_runner import cancel_agent_task, submit_task_async
from ._helpers import _user_id

router = Router(tags=["Agent 任务"], auth=JWTOrSessionAuth())


@router.post("/tasks", response=TaskOut)
async def submit_task(request: Any, payload: TaskIn) -> Any:  # pragma: no cover
    """提交一个后台任务：立即返回，agent 在后台跑，跑完通知。

    适合「这个案子帮我把材料梳理一遍」这类要跑几分钟、人不可能一直盯着的活。
    任务式运行没有 SSE 连接，因此高危工具会**挂起等离线审批**（见
    `GET /approvals/pending`），而不是被直接拒绝。
    """
    if not payload.message.strip():
        raise HttpError(400, "任务内容不能为空")
    session = await create_session_record(
        title=payload.title.strip() or payload.message.strip()[:30],
        user_id=_user_id(request),
        origin=AgentSession.Origin.TASK,
        case_id=payload.case_id,
        contract_id=payload.contract_id,
    )
    # 入队并在 service 层回写 task_id（API 层不碰 ORM）
    task_id = await submit_task_async(
        session=session,
        user_message=payload.message,
        user_id=_user_id(request),
    )
    return TaskOut(
        session_id=str(session.session_id),
        task_id=task_id,
        task_state=AgentSession.TaskState.QUEUED,
        title=session.title,
    )


@router.get("/tasks/{session_id}", response=TaskOut)
async def get_task_status(request: Any, session_id: str) -> Any:  # pragma: no cover
    """查询后台任务进度（前端轮询用）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "任务不存在")
    return TaskOut(
        session_id=str(session.session_id),
        task_id=session.task_id,
        task_state=session.task_state,
        title=session.title,
    )


@router.delete("/tasks/{session_id}")
async def cancel_task(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """取消后台任务（P1-4）。

    排队中：从 django-q 队列移除并置 cancelled；
    运行中：诚实告知暂不支持中途终止（pi 子进程在 worker 内，无跨进程
    abort 通道——见差距报告 P2），任务会跑到自然结束；
    已结束：如实返回终态。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "任务不存在")
    if session.origin != AgentSession.Origin.TASK or not session.task_id:
        raise HttpError(400, "该会话不是后台任务")
    if session.task_state not in (AgentSession.TaskState.QUEUED, AgentSession.TaskState.RUNNING):
        return {"success": False, "task_state": session.task_state, "message": "任务已结束，无需取消"}

    result = await sync_to_async(cancel_agent_task, thread_sensitive=True)(session)
    if not result["success"]:
        raise HttpError(409, result["message"])
    return result
