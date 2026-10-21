"""pi 事件 → 前端 SSE 事件桥接。

## 事件契约（前端消费的稳定接口）

    meta / activity / delta / tool_call / tool_result / approval_request
    error / done

## pi 的实际事件形态（1.3.0 实测）

pi 的 `message_update` 携带的是 **usage 统计**，不是文本增量；完整文本在
`message_end` 里一次性给出。因此增量输出需要对 `message_end` 做「与已发内容
求差」的处理，否则要么丢字，要么重复。

工具调用同样是成对的 `message_end`（assistant 带 toolCall / tool 带结果），
而非独立的 tool_call 事件。

映射原则：
- 只输出前端真正使用的字段
- 未识别事件静默丢弃（避免把内部诊断泄漏给浏览器）
- 审批不经事件流传递（走独立 HTTP 通道），由服务层推 `approval_request`
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from .rpc_client import PiEvent, PiRpcSession

logger = logging.getLogger(__name__)

_RESULT_PREVIEW_LIMIT = 2000


def _content_text(message: dict[str, Any]) -> str:
    """从 pi 的 message.content 里拼出纯文本。"""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _content_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """从 assistant 消息里取出工具调用列表。"""
    content = message.get("content")
    if not isinstance(content, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") in {"toolCall", "tool_call", "toolUse"}:
            calls.append(item)
    return calls


def _tool_name(record: dict[str, Any]) -> str:
    for key in ("toolName", "tool_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class DeltaTracker:
    """把「全文快照」转成「增量」的辅助器。

    pi 同时可能给两种形态：``message_update`` 的显式 delta、``message_end`` 的
    全文。两者会重叠，所以统一用「已发送长度」做水位：

    - ``note(delta)``：记下已直接发出的增量，推高水位
    - ``diff(full_text)``：只返回超出水位的部分
    """

    def __init__(self) -> None:
        self._sent = 0

    def note(self, delta: str) -> None:
        """记录已直接发出的增量长度。"""
        self._sent += len(delta)

    def diff(self, full_text: str) -> str:
        if not full_text:
            return ""
        if len(full_text) <= self._sent:
            return ""
        chunk = full_text[self._sent :]
        self._sent = len(full_text)
        return chunk

    def reset(self) -> None:
        self._sent = 0


def translate(
    event: PiEvent,
    *,
    agent: str = "pi",
    tracker: DeltaTracker | None = None,
) -> dict[str, Any] | None:
    """把一条 pi 记录翻成前端 SSE 事件；不需要外发时返回 ``None``。"""
    if event.kind == "extension_ui":
        # 审批走独立 HTTP 通道，扩展 UI 交互本轮不透传
        logger.debug("忽略 extension_ui 记录: %s", event.raw.get("method"))
        return None

    etype = event.event_type

    # ── 文本增量 ────────────────────────────────────────────────────────────
    if etype == "message_end":
        return _translate_message_end(event.raw, tracker)
    if etype == "message_update":
        return _translate_message_update(event.raw, tracker)

    # ── 工具事件（若 pi 某版本直接给）─────────────────────────────────────
    if etype in ("tool_call", "tool_execution_start"):
        return {
            "type": "tool_call",
            "tool_call_id": str(event.raw.get("toolCallId") or event.raw.get("id") or ""),
            "name": _tool_name(event.raw),
            "arguments": event.raw.get("input") or event.raw.get("arguments"),
        }
    if etype in ("tool_result", "tool_execution_end"):
        result = str(event.raw.get("result") or event.raw.get("output") or "")
        return {
            "type": "tool_result",
            "tool_call_id": str(event.raw.get("toolCallId") or event.raw.get("id") or ""),
            "name": _tool_name(event.raw),
            "result": result[:_RESULT_PREVIEW_LIMIT],
        }

    # ── 生命周期 ────────────────────────────────────────────────────────────
    if etype in ("agent_start", "turn_start", "step_start"):
        return {"type": "activity", "status": "thinking", "agent": agent}

    if etype == "error":
        return {"type": "error", "message": str(event.raw.get("message") or "pi 运行错误")}

    return None


def _translate_message_end(
    raw: dict[str, Any],
    tracker: DeltaTracker | None,
) -> dict[str, Any] | None:
    """处理 message_end：文本差量 + 工具调用/结果。"""
    message = raw.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")

    if role == "assistant":
        text = _content_text(message)
        if text and tracker is not None:
            chunk = tracker.diff(text)
            if chunk:
                return {"type": "delta", "content": chunk}
        calls = _content_tool_calls(message)
        if calls:
            call = calls[0]
            return {
                "type": "tool_call",
                "tool_call_id": str(call.get("id") or call.get("toolCallId") or ""),
                "name": str(call.get("name") or call.get("toolName") or ""),
                "arguments": call.get("input") or call.get("arguments"),
            }
        return None

    if role == "tool":
        # 工具结果消息：content 是工具输出文本
        return {
            "type": "tool_result",
            "tool_call_id": str(message.get("toolCallId") or message.get("id") or ""),
            "name": str(message.get("toolName") or ""),
            "result": _content_text(message)[:_RESULT_PREVIEW_LIMIT],
        }

    return None


def _translate_message_update(
    raw: dict[str, Any],
    tracker: DeltaTracker | None,
) -> dict[str, Any] | None:
    """处理 message_update：只认显式文本增量（``assistantMessageEvent.delta``）。

    pi 的 ``message_update`` 自带 message 快照时，其内容与 ``message_end`` 重复。
    为避免同一段文本发两次（实测「全链路联调成功」被推 3 次），
    这里统一交给 tracker 做差量，保证全局只发一次。
    """
    inner = raw.get("assistantMessageEvent") or {}
    if isinstance(inner, dict):
        delta = inner.get("delta")
        if isinstance(delta, str) and delta and tracker is not None:
            # 也走 tracker，防止与 message_end 的全文重复
            tracker.note(delta)
            return {"type": "delta", "content": delta}
    message = raw.get("message")
    if isinstance(message, dict) and tracker is not None:
        text = _content_text(message)
        chunk = tracker.diff(text)
        if chunk:
            return {"type": "delta", "content": chunk}
    return None


async def stream_events(
    session: PiRpcSession,
    *,
    agent: str = "pi",
) -> AsyncIterator[dict[str, Any]]:
    """把 pi 的事件流暴露成前端 SSE 事件流。

    ``agent_settled`` 是 pi 明确的「不会再有自动继续」边界，收到即结束。
    """
    tracker = DeltaTracker()
    async for event in session.drain_events():
        translated = translate(event, agent=agent, tracker=tracker)
        if translated is not None:
            yield translated
        if event.kind == "event" and event.event_type == "agent_settled":
            return
