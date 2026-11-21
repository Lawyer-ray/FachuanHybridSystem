"""消息与运行记录落库（原 chat_service.py 的持久化部分）。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
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


async def _persist_tool_message(
    session: AgentSession, event: dict[str, Any], agent_kind: str = "", turn_no: int = 0
) -> None:
    """落库工具结果（失败只记日志，不影响 SSE 流）。

    ``agent_kind``：双答轮次里两个 agent 各自调工具，回放时必须能分出哪条证据
    属于哪一栏（消息级来源见 ``AgentMessage.agent_kind``）。
    """
    try:
        await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.TOOL,
            content=str(event.get("result") or "")[:8000],
            tool_name=str(event.get("name") or ""),
            metadata={"tool_call_id": str(event.get("tool_call_id") or "")},
            agent_kind=agent_kind,
            turn_no=turn_no,
        )
    except Exception:
        logger.warning("工具消息落库失败", exc_info=True)


async def _stamp_finish_reason(*, message_ids: Mapping[str, Any], finish_reason: str) -> None:
    """把**轮级** ``finish_reason`` 回写到本轮已落库的助手消息（多答用）。

    为什么必须由整轮覆写、而不是各栏写自己的：``degraded`` 是**轮级**事实
    （「另外几栏没跑成」），单栏视角永远只会说 ok/error。前端
    ``turn-actions.canContinue`` 靠这个值决定「继续生成」能不能点，而历史回放
    没有 SSE 可看——只有这一份 metadata。

    Args:
        message_ids: ``kind -> StreamMemo``（只用它的 ``message_id`` / ``metadata``）。
            这里不直接收 ``StreamMemo``：``persist`` 被 ``multi`` / ``stream`` 共同
            依赖，反向 import 会形成环。
        finish_reason: 轮级结论（``ok`` / ``degraded`` / ``error``）。
    """
    for agent, memo in message_ids.items():
        message_id = getattr(memo, "message_id", None)
        if not message_id:
            # 这一栏没有正文（或落库失败 / 被取消）：没有可回写的行。
            continue
        metadata = {**getattr(memo, "metadata", {}), "finish_reason": finish_reason}
        try:
            await AgentMessage.objects.filter(pk=message_id).aupdate(metadata=metadata)
        except Exception:
            # 回写失败不能拖垮对话：done 仍要发（它是前端收栏的唯一信号）。
            logger.warning(
                "finish_reason 回写失败 message_id=%s agent=%s（不影响对话）", message_id, agent, exc_info=True
            )


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
    agent_kind: str = "",
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
    turn_no: int = 0,
) -> None:
    """落一条 AgentRun。任何失败只记日志——统计不能拖垮对话本身。"""
    if cancelled:
        status = AgentRun.Status.CANCELLED
    elif error_kind:
        status = AgentRun.Status.ERROR
    else:
        status = AgentRun.Status.OK
    try:
        from apps.core.llm.provider_lookup import resolve_provider_name

        await AgentRun.objects.acreate(
            session=session,
            user_id=user_id,
            provider=resolve_provider_name(model),
            model=(model or "")[:100],
            agent_kind=(agent_kind or "")[:32],
            status=status,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            cache_read_tokens=max(0, int(cache_read_tokens)),
            cache_write_tokens=max(0, int(cache_write_tokens)),
            tool_calls=max(0, int(tool_calls)),
            duration_ms=max(0, int(duration_ms)),
            error_kind=error_kind[:64],
            turn_no=turn_no,
            context_used_tokens=context_used_tokens,
            context_total_tokens=context_total_tokens,
        )
    except Exception:
        logger.warning("AgentRun 落库失败（不影响对话）", exc_info=True)
