"""pi 事件 → 前端 SSE 事件桥接。

事件契约（前端消费的稳定接口）：

    meta / activity / delta / tool_call / tool_result / approval_request
    error / done

映射原则：
- 只输出前端真正使用的字段
- 未识别的 pi 事件静默丢弃（避免把内部诊断泄漏给浏览器）
- 审批不经事件流传递（走独立 HTTP 通道），但 ``approval_request`` 由服务层推入
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from .rpc_client import PiEvent, PiRpcSession

logger = logging.getLogger(__name__)

_RESULT_PREVIEW_LIMIT = 2000


def _extract_text(record: dict[str, Any]) -> str:
    """从 pi 的 message_update 里取增量文本。"""
    inner = record.get("assistantMessageEvent") or record.get("event") or {}
    if isinstance(inner, dict):
        for key in ("delta", "text"):
            value = inner.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("delta", "text"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _tool_name(record: dict[str, Any]) -> str:
    for key in ("toolName", "tool_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    inner = record.get("toolCall") or {}
    if isinstance(inner, dict):
        for key in ("name", "toolName"):
            value = inner.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _tool_args(record: dict[str, Any]) -> Any:
    for key in ("input", "arguments", "args"):
        if key in record:
            return record[key]
    inner = record.get("toolCall") or {}
    if isinstance(inner, dict):
        return inner.get("input") or inner.get("arguments")
    return None


def _tool_id(record: dict[str, Any]) -> str:
    for key in ("toolCallId", "tool_call_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def translate(event: PiEvent, *, agent: str = "pi") -> dict[str, Any] | None:
    """把一条 pi 记录翻成前端 SSE 事件；不需要外发时返回 ``None``。"""
    if event.kind == "extension_ui":
        # 审批走独立 HTTP 通道，扩展 UI 交互本轮不透传
        logger.debug("忽略 extension_ui 记录: %s", event.raw.get("method"))
        return None

    etype = event.event_type

    if etype in ("message_update", "message_delta"):
        text = _extract_text(event.raw)
        return {"type": "delta", "content": text} if text else None

    if etype in ("tool_call", "tool_execution_start"):
        return {
            "type": "tool_call",
            "tool_call_id": _tool_id(event.raw),
            "name": _tool_name(event.raw),
            "arguments": _tool_args(event.raw),
        }

    if etype in ("tool_result", "tool_execution_end"):
        result = str(event.raw.get("result") or event.raw.get("output") or "")
        return {
            "type": "tool_result",
            "tool_call_id": _tool_id(event.raw),
            "name": _tool_name(event.raw),
            "result": result[:_RESULT_PREVIEW_LIMIT],
        }

    if etype in ("agent_start", "turn_start", "step_start"):
        return {"type": "activity", "status": "thinking", "agent": agent}

    if etype == "error":
        return {"type": "error", "message": str(event.raw.get("message") or "pi 运行错误")}

    return None


async def stream_events(
    session: PiRpcSession,
    *,
    agent: str = "pi",
) -> AsyncIterator[dict[str, Any]]:
    """把 pi 的事件流暴露成前端 SSE 事件流。

    ``agent_settled`` 是 pi 明确的「不会再有自动继续」边界，收到即结束。
    """
    async for event in session.drain_events():
        translated = translate(event, agent=agent)
        if translated is not None:
            yield translated
        if event.kind == "event" and event.event_type == "agent_settled":
            return
