"""任务式（后台）入口 —— 挂上去跑，回来收结果。

## 为什么需要它

对话式入口要求「用户开着页面盯着」：SSE 连着、审批能弹窗、随时可插话。
但律师的真实场景常常是「这个案子帮我把材料梳理一遍」——这种活要跑几分钟，
人不可能一直盯着。没有后台入口，用户只能等，或者干脆不用。

## 与对话式入口的差别

| | 对话式 | **任务式** |
|:-|:-|:-|
| 触发 | POST 消息，SSE 占着连接 | 提交后立即返回，后台跑 |
| 用户在线 | 必须（审批弹窗、插话） | 不必 |
| 高危工具 | 弹窗审批 | 无人可问 → 挂起等离线审批（见 approval.py） |
| 结果 | 边流边看 | 跑完落库 + 通知 |

## 为什么复用 stream_chat

后台跑和前台跑是**同一套编排**：同样的历史、审批、上下文、成本记录。单独写
一条路径等于把审批漏判、把 AgentRun 漏记这些坑再踩一遍。这里只做三件事：
把事件流抽干（后台没有前端消费）、更新任务状态、完成后通知。

## 为什么用 django-q

项目已有 django-q 集群在跑（`apps/core/tasking`）。不引入新依赖，也天然获得
任务 id、失败重试与运维可见性（管理端能查到这个任务）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.utils import timezone

from ..models import AgentMessage, AgentSession

logger = logging.getLogger(__name__)

#: 任务式单轮超时（秒）。后台任务要长一些：法律材料梳理常见 10 分钟以上。
TASK_TIMEOUT = 1800.0


def enqueue_task(*, session: AgentSession, user_message: str, user_id: int | None) -> str:
    """把一次 agent 运行丢到后台，返回 django-q 的 task id。

    调用方（API）只负责建会话 + 调这里，立即返回；前端通过会话的
    ``task_state`` / ``task_id`` 轮询进度，或用 ``/approvals/pending`` 处理
    离线审批。

    Args:
        session: 已创建的 ``origin=task`` 会话。
        user_message: 用户需求。
        user_id: 发起人（决定工具以谁的身份执行）。

    Returns:
        django-q task id（用于查询 / 取消）。

    Note:
        内部是同步 ORM + django-q 入队。**异步调用方**（Ninja 端点）必须用
        ``submit_task_async`` 包一层，否则抛 ``SynchronousOnlyOperation``。
    """
    # 走统一入口：业务层不得直接依赖 django-q（未来换 Celery 只改 core.tasking）
    from apps.core.tasking import submit_task

    session_id = str(session.session_id)
    AgentSession.objects.filter(pk=session.pk).update(task_state=AgentSession.TaskState.QUEUED)

    task_id = submit_task(
        "apps.agent.services.task_runner.run_agent_task",
        session_id,
        user_message,
        user_id,
        task_name=f"agent-task:{session_id}",
        timeout=int(TASK_TIMEOUT),
    )
    AgentSession.objects.filter(pk=session.pk).update(task_id=str(task_id))
    logger.info("agent 任务已入队 session=%s task=%s", session_id, task_id)
    return str(task_id)


def run_agent_task(session_id: str, user_message: str, user_id: int | None) -> dict[str, Any]:
    """后台执行一轮 agent（django-q worker 内调用，**同步**函数）。

    内部跑 ``stream_chat`` 并抽干事件流——后台没有前端消费，但事件仍然要过一遍：
    ``tool_result`` 的落库、``usage`` 的累加、``AgentRun`` 的记录都在那条路径上。

    Returns:
        ``{"session_id", "state", "error", "chars"}``，便于在管理端看结果。
    """
    session = AgentSession.objects.filter(session_id=session_id).first()
    if session is None:
        logger.warning("agent 任务找不到会话 session=%s", session_id)
        return {"session_id": session_id, "state": "failed", "error": "会话不存在"}

    AgentSession.objects.filter(pk=session.pk).update(task_state=AgentSession.TaskState.RUNNING)

    chars = 0
    error = ""
    try:
        chars = _drain_stream(session, user_message, user_id)
    # 后台任务必须收口所有异常，否则任务状态会永远卡在 running
    except Exception as exc:
        error = _humanize(exc)
        logger.exception("agent 任务执行失败 session=%s", session_id)

    state = AgentSession.TaskState.FAILED if error else AgentSession.TaskState.SUCCEEDED
    AgentSession.objects.filter(pk=session.pk).update(
        task_state=state,
        task_finished_at=timezone.now(),
        task_error=error[:255],
    )
    _notify_completion(session=session, state=state, error=error, chars=chars)
    return {"session_id": session_id, "state": state, "error": error, "chars": chars}


def _drain_stream(session: AgentSession, user_message: str, user_id: int | None) -> int:
    """在同步上下文里跑完 ``stream_chat``，返回产出的正文字符数。

    用 ``asyncio.run``：django-q worker 是同步的，而 stream_chat 是异步生成器。
    这与项目里其他后台任务（gsxt 登录、报表生成）的做法一致。
    """
    from .chat_service import close_pool, stream_chat

    async def _run() -> int:
        chars = 0
        try:
            async for event in stream_chat(session=session, user_message=user_message, user_id=user_id):
                if event.get("type") == "delta":
                    chars += len(str(event.get("content") or ""))
        finally:
            # 后台任务跑完就释放进程池：worker 进程可能长期存活，
            # 不关会把 pi 子进程留到进程退出。
            await close_pool()
        return chars

    return asyncio.run(_run())


def _humanize(exc: Exception) -> str:
    """把异常翻成用户能看懂的一句话（不泄露堆栈 / 内部路径）。"""
    from ..pi.pool import PoolQueueTimeoutError
    from ..pi.rpc_client import PiError, PiNotAvailableError

    if isinstance(exc, PiNotAvailableError):
        return "AI 运行时不可用，请联系管理员"
    if isinstance(exc, PoolQueueTimeoutError):
        return "当前使用人数较多，请稍后重试"
    if isinstance(exc, PiError):
        return "AI 运行失败，请稍后重试"
    return "任务执行失败，请稍后重试"


def _notify_completion(*, session: AgentSession, state: str, error: str, chars: int) -> None:
    """给发起人投递「跑完了」的通知。

    为什么必须通知：任务式入口的全部价值就是「人不在也能跑」。跑完不告诉用户，
    等于他得自己回来一个个点开看，还不如盯着。

    投递方式：写一条 ``AgentMessage``（system 提示语），让会话列表与回放里
    直接看得到结果状态——不引入新的通知表，也不依赖用户开着页面。
    失败只记日志：通知发不出去不能让已经成功的任务变成失败。
    """
    try:
        title = session.title or "后台任务"
        if state == AgentSession.TaskState.SUCCEEDED:
            text = f"【后台任务完成】{title}\n已生成回答（{chars} 字），可直接查看。"
        else:
            text = f"【后台任务失败】{title}\n原因：{error or '未知错误'}"
        AgentMessage.objects.create(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            content=text,
            metadata={"kind": "task_notification", "state": state},
        )
        AgentSession.objects.filter(pk=session.pk).update(notified=True)
    except Exception:
        logger.warning("任务完成通知写入失败 session=%s", session.session_id, exc_info=True)


async def submit_task_async(*, session: AgentSession, user_message: str, user_id: int | None) -> str:
    """``enqueue_task`` 的异步包装（Ninja 异步端点用）。

    入队要读会话、更新状态、写 django-q 队列——都是同步 IO，必须放线程里跑。
    """
    from asgiref.sync import sync_to_async

    return await sync_to_async(enqueue_task, thread_sensitive=True)(
        session=session,
        user_message=user_message,
        user_id=user_id,
    )
