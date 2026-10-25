"""子 agent 派发与结果回收。

设计约束（读代码前先看这三条，否则很容易做出一个把系统拖垮的实现）：

## 1. 子任务走后台队列，不占主会话的进程池槽位

法穿的池只有 4 个槽（`FACHUAN_AGENT_POOL_SIZE`）。如果子 agent 在主会话的
调用栈里同步 `acquire()`，主会话自己就会因为抢不到槽而死等——「派个子任务
反而把自己卡死」。所以子任务一律走 django-q 后台跑，主会话只是**挂起等结果**
（`asyncio.Event` + 轮询 `AgentSubtask.status`），不持有 pi 进程。

## 2. 只读工具白名单是结构性安全，不是提示词劝阻

子会话只允许 `get_* / list_* / search_* / read_*`。研究类子任务在设计上
就没有写能力——中途从网页/卷宗里抓到的提示注入**没有可作用的对象**。
这比「事后检测注入」可靠得多。

白名单在**起 pi 进程时**用 `--tools` 收窄，不是靠系统提示词叮嘱。

## 3. 总预算闸必须有

一次主会话最多 3 个并发子任务、每个最多 8 轮、单任务 token 上限。
不设的话：4 个并发请求 × 4 个子 agent = 16 路打共享 MCP，
而 MCP 背后是**真实数据库**。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from django.utils import timezone

from ..models import AgentMessage, AgentRun, AgentSession, AgentSubtask

logger = logging.getLogger(__name__)

#: 子会话可用的工具前缀（结构性只读）。
READONLY_PREFIXES: tuple[str, ...] = ("get_", "list_", "search_", "read_", "preview_")

#: 一次主会话最多同时派几个子任务
MAX_CONCURRENT_SUBTASKS = 3
#: 单个子任务最多几轮模型调用（防失控）
MAX_TURNS_PER_SUBTASK = 8
#: 等待子任务完成的上限（秒）
SUBTASK_WAIT_TIMEOUT = 300.0
#: 轮询间隔（秒）—— 后台任务状态变化不频繁，1 秒足够且不压库
POLL_INTERVAL = 1.0


def readonly_tool_selection() -> str:
    """子会话的 ``--tools`` 参数（只读白名单）。

    返回形如 ``mcp__fachuan__get_*,mcp__fachuan__list_*,...``。
    刻意**不含** ``tool_search``——子 agent 不该自己发现新工具，它拿到的
    就是一份固定的只读面。
    """
    return ",".join(f"mcp__fachuan__{prefix}*" for prefix in READONLY_PREFIXES)


async def count_running(parent_session_pk: int) -> int:
    """主会话当前在跑的子任务数（预算闸用）。"""
    return await AgentSubtask.objects.filter(
        parent_session_id=parent_session_pk,
        status__in=(AgentSubtask.Status.QUEUED, AgentSubtask.Status.RUNNING),
    ).acount()


async def dispatch(
    *,
    parent_session: AgentSession,
    prompt: str,
    user_id: int | None = None,
    kind: str = AgentSubtask.Kind.RESEARCH,
) -> AgentSubtask:
    """派发一个子任务（创建子会话 + 入队）。

    Raises:
        ValueError: 超并发上限 / prompt 为空 / 主会话不存在。
    """
    text = (prompt or "").strip()
    if not text:
        raise ValueError("子任务必须给出 prompt（要查什么、要回答什么）")
    if len(text) > 4000:
        raise ValueError("子任务 prompt 过长（>4000 字）。请把它拆成更聚焦的几个子任务")

    running = await count_running(parent_session.pk)
    if running >= MAX_CONCURRENT_SUBTASKS:
        raise ValueError(
            f"同时最多派 {MAX_CONCURRENT_SUBTASKS} 个子任务（当前 {running} 个在跑）。"
            f"请等前面的完成，或把它们合并成一个更聚焦的任务。"
        )

    # 子会话：独立 pi session 目录 + 独立消息表，origin 标记为 subtask
    child = await AgentSession.objects.acreate(
        title=f"子任务：{text[:28]}",
        user_id=user_id,
        origin=AgentSession.Origin.SUBTASK,
        case_id=parent_session.case_id,
        contract_id=parent_session.contract_id,
    )
    subtask = await AgentSubtask.objects.acreate(
        parent_session=parent_session,
        child_session=child,
        user_id=user_id,
        kind=kind,
        prompt=text,
    )

    # 入队（走统一入口 apps.core.tasking：业务层不得直接依赖 django-q，
    # 将来换 Celery 只改那一处）。
    try:
        from apps.core.tasking import submit_task

        submit_task(
            "apps.agent.services.subtask_runner.run_subtask",
            str(subtask.subtask_id),
            task_name=f"agent-subtask:{subtask.subtask_id}",
            timeout=int(SUBTASK_WAIT_TIMEOUT + 120),
        )
    except Exception:
        # 入队失败必须显式落败，不能让主会话等到超时才知道
        logger.exception("子任务入队失败: %s", subtask.subtask_id)
        subtask.status = AgentSubtask.Status.FAILED
        subtask.error = "子任务入队失败（后台队列不可用）"
        subtask.finished_at = timezone.now()
        await subtask.asave(update_fields=["status", "error", "finished_at"])
    return subtask


async def wait_for_result(
    subtask_id: uuid.UUID,
    timeout: float = SUBTASK_WAIT_TIMEOUT,
) -> dict[str, Any]:
    """挂起等待子任务完成（不占 pi 进程槽位）。

    为什么轮询而不用 `asyncio.Event`：子任务跑在**另一个进程**（django-q
    worker），进程内事件无法跨进程。轮询数据库是唯一可靠方式，间隔 1 秒
    对状态变化频率来说足够。
    """
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        record = await AgentSubtask.objects.filter(subtask_id=subtask_id).afirst()
        if record is None:
            return {"status": "failed", "error": "子任务记录不存在"}
        if record.status != last_status:
            last_status = record.status
            logger.info("子任务状态: %s -> %s", subtask_id, record.status)
        if record.status in (
            AgentSubtask.Status.SUCCEEDED,
            AgentSubtask.Status.FAILED,
            AgentSubtask.Status.CANCELLED,
        ):
            return _format_result(record)
        await asyncio.sleep(POLL_INTERVAL)

    # 超时：标记并返回「部分结果」——绝不让主 agent 把半成品当成品
    await AgentSubtask.objects.filter(
        subtask_id=subtask_id, status__in=(AgentSubtask.Status.QUEUED, AgentSubtask.Status.RUNNING)
    ).aupdate(status=AgentSubtask.Status.TIMEOUT, finished_at=timezone.now())
    record = await AgentSubtask.objects.filter(subtask_id=subtask_id).afirst()
    partial = _format_result(record) if record else {}
    partial["status"] = "timeout"
    partial["hint"] = (
        f"子任务超过 {int(timeout)} 秒未完成，已标记超时。请基于现有信息继续，或把它拆成更小的子任务重派。"
    )
    return partial


def _format_result(record: AgentSubtask) -> dict[str, Any]:
    """把子任务记录格式化成给主 agent 看的结构。

    刻意**返回成本**：主 agent 据此判断「这次调研值不值」，也便于它决定
    要不要再派一个（预算感知）。
    """
    base: dict[str, Any] = {
        "status": record.status,
        "tokens": record.tokens,
        "duration_ms": record.duration_ms,
    }
    if record.status == AgentSubtask.Status.SUCCEEDED:
        base["result"] = record.result
    elif record.status == AgentSubtask.Status.FAILED:
        base["error"] = record.error or "子任务失败（无错误详情）"
        base["hint"] = "子任务失败了。请换一种查法，或直接告诉律师「这项检索没做成」。"
    elif record.status == AgentSubtask.Status.CANCELLED:
        base["hint"] = "子任务被取消。"
    return base


def readonly_prefixes_doc() -> str:
    """给工具描述用的白名单说明（避免文档与实现漂移）。"""
    names = "、".join(p.rstrip("_") for p in READONLY_PREFIXES)
    return f"子 agent 只能调用 {names} 开头的只读工具"


def extract_final_answer(child_session: AgentSession) -> tuple[str, int]:
    """从子会话的 AgentMessage 读最后一条 assistant 消息（原文）。

    为什么从表里读而不是从 SSE 拼：SSE 是流式增量，可能丢帧、可能被客户端
    断开截断；`AgentMessage` 是落库的审计权威。这与既有「审计以表为准」
    的设计一致。

    Returns:
        ``(文本, 输入+输出 token)``。
    """
    last = (
        AgentMessage.objects.filter(session=child_session, role=AgentMessage.Role.ASSISTANT)
        .order_by("-created_at")
        .first()
    )
    if last is None:
        return "", 0
    meta = last.metadata if isinstance(last.metadata, dict) else {}
    tokens = int(meta.get("output_tokens") or 0)
    run = AgentRun.objects.filter(session=child_session).order_by("-created_at").first()
    if run is not None:
        tokens = run.total_tokens
    return last.content, tokens
