"""子 agent 后台执行器（django-q worker 内运行）。

## 为什么单独一个模块

`task_runner.run_agent_task` 是「任务式后台入口」的实现，服务的是律师主动
挂后台的长任务；本模块服务的是**主 agent 派出的只读调研子任务**。两者共享
`stream_chat` 这条唯一执行路径（审批、成本、落库都不能重写一遍），但入口、
工具面、失败处置完全不同：

| | task_runner | subtask_runner |
|:-|:-|:-|
| 谁发起 | 律师 | 主 agent |
| 工具面 | 全量业务工具 | **只读白名单** |
| 会话可见性 | 出现在会话列表 | 隐藏（origin=subtask） |
| 失败处置 | 写通知消息给律师 | 回传给主 agent，由它决定怎么说 |

## 为什么不在这里做「多子任务并发」

django-q 的并发由 worker 数量决定，这里再开线程只会把共享 MCP 打爆
（背后是真实数据库）。**并发闸在主会话那侧**（`subtask.dispatch` 的
`MAX_CONCURRENT_SUBTASKS`），本模块只负责「跑好这一个」。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from django.utils import timezone

from ..models import AgentSession, AgentSubtask
from . import subtask as subtask_service

logger = logging.getLogger(__name__)

#: 子任务单轮超时（秒）。比任务式短：子任务是「查一下」，不是「梳理全部材料」。
SUBTASK_RUN_TIMEOUT = 300.0


def run_subtask(subtask_id: str) -> dict[str, Any]:
    """后台跑一个子任务（django-q worker 内调用的**同步**函数）。

    所有异常必须在这里收口——否则子任务状态会永远卡在 running，
    主 agent 那边会一直等到超时。
    """
    try:
        record = (
            AgentSubtask.objects.select_related("child_session", "parent_session")
            .filter(subtask_id=uuid.UUID(subtask_id))
            .first()
        )
    except (ValueError, AttributeError):
        logger.warning("子任务 id 非法: %s", subtask_id)
        return {"subtask_id": subtask_id, "state": "failed", "error": "id 非法"}

    if record is None:
        logger.warning("子任务不存在: %s", subtask_id)
        return {"subtask_id": subtask_id, "state": "failed", "error": "子任务不存在"}
    if record.status not in (AgentSubtask.Status.QUEUED, AgentSubtask.Status.RUNNING):
        # 已被取消/超时：不要覆盖已有结论
        logger.info("子任务状态为 %s，跳过执行: %s", record.status, subtask_id)
        return {"subtask_id": subtask_id, "state": record.status}

    child = record.child_session
    if child is None:
        _finish(record, AgentSubtask.Status.FAILED, error="子会话已被删除")
        return {"subtask_id": subtask_id, "state": "failed", "error": "子会话已被删除"}

    AgentSubtask.objects.filter(pk=record.pk).update(status=AgentSubtask.Status.RUNNING)
    started = time.monotonic()

    try:
        chars = _drain(child, record)
    except Exception as exc:
        logger.exception("子任务执行失败: %s", subtask_id)
        _finish(
            record,
            AgentSubtask.Status.FAILED,
            error=_humanize(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return {"subtask_id": subtask_id, "state": "failed", "error": _humanize(exc)}

    text, tokens = subtask_service.extract_final_answer(child)
    duration_ms = int((time.monotonic() - started) * 1000)
    if not text.strip():
        _finish(
            record,
            AgentSubtask.Status.FAILED,
            error="子 agent 没有产出任何答复（可能工具面过窄或模型未响应）",
            tokens=tokens,
            duration_ms=duration_ms,
        )
        return {"subtask_id": subtask_id, "state": "failed", "error": "无答复"}

    _finish(
        record,
        AgentSubtask.Status.SUCCEEDED,
        result=text.strip()[:20000],
        tokens=tokens,
        duration_ms=duration_ms,
    )
    logger.info("子任务完成: %s (%d 字, %d tokens, %dms)", subtask_id, len(text), tokens, duration_ms)
    return {"subtask_id": subtask_id, "state": "succeeded", "chars": chars}


def _drain(child: AgentSession, record: AgentSubtask) -> int:
    """跑一轮 ``stream_chat`` 并抽干事件流（后台没有前端消费）。

    为什么仍然要抽干：`tool_result` 落库、`usage` 累加、`AgentRun` 记录
    都在那条事件路径上——跳过就等于子任务不产生审计与成本记录。

    工具面在这里收窄为只读白名单（`readonly_tool_selection`）。这是**结构性**
    安全：子 agent 的进程里压根没有写工具可调，中途抓到的提示注入没有
    可作用的对象。
    """
    from .chat_service import stream_chat

    selection = subtask_service.readonly_tool_selection()

    async def _run() -> int:
        count = 0
        async for _event in stream_chat(
            session=child,
            user_message=record.prompt,
            user_id=record.user_id,
            tool_selection=selection,
        ):
            count += 1
        return count

    return asyncio.run(_run())


def _finish(
    record: AgentSubtask,
    status: str,
    *,
    result: str = "",
    error: str = "",
    tokens: int = 0,
    duration_ms: int = 0,
) -> None:
    """收尾落库（幂等：已被取消/超时的不覆盖）。"""
    AgentSubtask.objects.filter(pk=record.pk).update(
        status=status,
        result=result,
        error=error,
        tokens=tokens,
        duration_ms=duration_ms,
        finished_at=timezone.now(),
    )


def _humanize(exc: BaseException) -> str:
    """把异常翻成人话（不含堆栈）：子任务的错误会进主 agent 上下文。"""
    name = type(exc).__name__
    if "QueueTimeout" in name or "queue_timeout" in str(exc).lower():
        return "系统繁忙（agent 进程池排队超时），请稍后重试"
    if "PiNotAvailable" in name:
        return "AI 运行时不可用"
    if "PiError" in name:
        return f"AI 运行时出错：{exc}"
    text = str(exc).strip()
    if text and len(text) <= 200:
        return text
    return f"{name}（子任务执行失败）"
