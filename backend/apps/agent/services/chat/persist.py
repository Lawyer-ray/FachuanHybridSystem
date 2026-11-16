"""消息与运行记录落库（原 chat_service.py 的持久化部分）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...models import AgentMessage, AgentRun, AgentSession

logger = logging.getLogger(__name__)


def _log_task_failure(task: asyncio.Task[Any]) -> None:
    """取消路径里派发的落库任务：失败只记日志（已无响应通道可报）。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("取消路径助手消息落库失败", exc_info=exc)


async def _recent_history(session: AgentSession, limit: int = 40) -> list[AgentMessage]:
    """取最近若干条历史消息（倒序取再反转，避免全表加载）。"""
    rows = AgentMessage.objects.filter(session=session).order_by("-created_at", "-id")[:limit]
    messages = [m async for m in rows]
    messages.reverse()
    return messages


async def _persist_tool_message(session: AgentSession, event: dict[str, Any]) -> None:
    """落库工具结果（失败只记日志，不影响 SSE 流）。"""
    try:
        await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.TOOL,
            content=str(event.get("result") or "")[:8000],
            tool_name=str(event.get("name") or ""),
            metadata={"tool_call_id": str(event.get("tool_call_id") or "")},
        )
    except Exception:
        logger.warning("工具消息落库失败", exc_info=True)


async def _persist_compaction_message(session: AgentSession, label: str) -> None:
    """落库一条压缩留痕（自动 / 手动共用；失败只记日志）。"""
    try:
        await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.TOOL,
            content=label,
            tool_name="context_compaction",
            metadata={},
        )
    except Exception:
        logger.warning("压缩留痕消息落库失败", exc_info=True)


async def _record_run(
    *,
    session: AgentSession,
    user_id: int | None,
    model: str | None,
    cancelled: bool,
    error_kind: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    tool_calls: int,
    duration_ms: int,
    context_used_tokens: int | None = None,
    context_total_tokens: int | None = None,
) -> None:
    """落一条 AgentRun。任何失败只记日志——统计不能拖垮对话本身。"""
    if cancelled:
        status = AgentRun.Status.CANCELLED
    elif error_kind:
        status = AgentRun.Status.ERROR
    else:
        status = AgentRun.Status.OK
    try:
        await AgentRun.objects.acreate(
            session=session,
            user_id=user_id,
            model=(model or "")[:100],
            status=status,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            cache_read_tokens=max(0, int(cache_read_tokens)),
            cache_write_tokens=max(0, int(cache_write_tokens)),
            tool_calls=max(0, int(tool_calls)),
            duration_ms=max(0, int(duration_ms)),
            error_kind=error_kind[:64],
            context_used_tokens=context_used_tokens,
            context_total_tokens=context_total_tokens,
        )
    except Exception:
        logger.warning("AgentRun 落库失败（不影响对话）", exc_info=True)
