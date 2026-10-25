"""pi 事件 → 前端 SSE 事件桥接。

## 事件契约（前端消费的稳定接口）

    meta / activity / delta / thinking / tool_call / tool_result / usage
    approval_request / error / done

## pi 的实际事件形态（1.4.0 实测，fixture 见 tests/ci/fixtures/agent/）

1.4.0 把 `message_update` 改成 **delta-only**（`docs/json.md`）：不再带 `message`
快照，也不再带 `assistantMessageEvent.partial`。`assistantMessageEvent.type`
是一套完整的分块生命周期：

    text_start   {contentIndex}
    text_delta   {contentIndex, delta}          ← 增量文本
    text_end     {contentIndex, content}        ← 权威全文（用于校正）
    thinking_*   / toolcall_start / toolcall_delta / toolcall_end

实测要点（不要凭想象补）：

- `text_end` 带的是 ``content`` 而不是 ``delta``；`toolcall_start` 带
  ``id``/``toolName``，`toolcall_end` 带完整 ``toolCall``；
  `toolcall_delta` 的 ``delta`` 是**参数的 JSON 片段**，绝不可当正文发给前端
  （曾把 ``{"path": "`` 混进用户看到的回答里）。
- 工具结果的消息角色是 **``toolResult``**（不是 ``tool``），字段是
  ``toolCallId`` / ``toolName``；结果在 `tool_execution_end` 的 ``result`` 里是
  一个 **dict**（``{content: [...], structuredContent: ...}``），直接 ``str()``
  会把 Python repr 泄给前端。
- ``usage`` 在 `message_update` 顶层（文本结束时才有值）和 `message_end` 的
  ``message.usage`` 里都有。

因此本模块的三条纪律：

1. 正文只认 ``text_delta``；``text_end``/``message_end`` 只用来**校正**，不重复发。
2. 工具调用/结果只从**一条**路径产出（优先 ``toolcall_end`` /
   ``tool_execution_end``），避免重复。
3. 未识别事件静默丢弃（避免把内部诊断泄漏给浏览器）；
   审批不经事件流传递（走独立 HTTP 通道），由服务层推 `approval_request`。
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


def _tool_result_text(result: Any) -> str:
    """把工具结果规整成可展示的文本。

    ``tool_execution_end`` 的 ``result`` 是 dict（MCP 返回的形状）：
    ``{"content": [{"type": "text", "text": "..."}], "structuredContent": ...}``。
    直接 ``str()`` 会把 Python repr 泄给前端。
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "".join(item if isinstance(item, str) else _tool_result_text(item) for item in result)
    if not isinstance(result, dict):
        return "" if result is None else str(result)
    content = result.get("content")
    if content is not None:
        text = _content_text({"content": content})
        if text:
            return text
    structured = result.get("structuredContent")
    if isinstance(structured, str):
        return structured
    return ""


def _tool_call_event(call: dict[str, Any]) -> dict[str, Any]:
    """规整一条 tool_call 事件。"""
    return {
        "type": "tool_call",
        "tool_call_id": str(call.get("id") or call.get("toolCallId") or ""),
        "name": str(call.get("name") or call.get("toolName") or ""),
        "arguments": call.get("arguments") if call.get("arguments") is not None else call.get("input"),
    }


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
    """把「全文快照」转成「增量」的辅助器，兼去重工具调用。

    pi 同时可能给两种形态：``message_update`` 的显式 delta、``message_end`` 的
    全文。两者会重叠，所以统一用「已发送长度」做水位：

    - ``note(delta)``：记下已直接发出的增量，推高水位
    - ``diff(full_text)``：只返回超出水位的部分

    工具调用同理：``toolcall_end`` 已经发过带完整参数的 tool_call，
    ``message_end`` 里同一 id 就不得再发（否则前端会看到两条，
    且后一条的 arguments 常常是 None）。
    """

    def __init__(self) -> None:
        self._sent = 0
        self._tool_calls: set[str] = set()
        self._tool_results: set[str] = set()

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

    def mark_tool_call(self, call_id: str) -> None:
        """记下已发过的 tool_call id。"""
        if call_id:
            self._tool_calls.add(call_id)

    def tool_call_sent(self, call_id: str) -> bool:
        """该 tool_call 是否已经发过。"""
        return bool(call_id) and call_id in self._tool_calls

    def mark_tool_result(self, call_id: str) -> None:
        """记下已发过的 tool_result id（tool_execution_end 与 message_end 会重叠）。"""
        if call_id:
            self._tool_results.add(call_id)

    def tool_result_sent(self, call_id: str) -> bool:
        """该 tool_result 是否已经发过。"""
        return bool(call_id) and call_id in self._tool_results

    def reset(self) -> None:
        """复位正文水位（每条 assistant 消息一次）；工具调用记录不跟着清。

        工具调用在 message_end 里还要用于去重，而 message_start(message_end)
        之间可能隔着多次复位；这里只清正文水位。
        """
        self._sent = 0


def translate(
    event: PiEvent,
    *,
    agent: str = "pi",
    tracker: DeltaTracker | None = None,
) -> dict[str, Any] | None:
    """把一条 pi 记录翻成前端 SSE 事件；不需要外发时返回 ``None``。

    一条记录可能产出多个事件（assistant 消息同时带文本和工具调用），
    完整结果用 :func:`translate_all`；本函数返回第一个，供单测断言。
    """
    events = translate_all(event, agent=agent, tracker=tracker)
    return events[0] if events else None


def translate_all(
    event: PiEvent,
    *,
    agent: str = "pi",
    tracker: DeltaTracker | None = None,
) -> list[dict[str, Any]]:
    """把一条 pi 记录翻成零到多个前端 SSE 事件。"""
    if event.kind == "extension_ui":
        # 审批走独立 HTTP 通道，扩展 UI 交互本轮不透传
        logger.debug("忽略 extension_ui 记录: %s", event.raw.get("method"))
        return []

    etype = event.event_type

    # ── 消息边界：每条 assistant 消息开始时复位水位 ─────────────────────────
    # 一个 run 内会有多段 assistant 文本（工具循环的常态）。水位是「本条消息
    # 已发送长度」，跨消息累计会把第二段短文本整段吞掉、长文本截掉开头。
    if etype == "message_start":
        message = event.raw.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant" and tracker is not None:
            tracker.reset()
        return []

    # ── 文本增量 ────────────────────────────────────────────────────────────
    if etype == "message_end":
        return _translate_message_end(event.raw, tracker)
    if etype == "message_update":
        return _translate_message_update(event.raw, tracker)

    # ── 工具执行事件（结果的权威来源）────────────────────────────────────
    # tool_execution_* 与 toolcall_end 讲的是同一次调用，必须去重：
    # toolcall_end 带完整 arguments，tool_execution_start 只带已解析的 args。
    # 以 toolcall_end 为准，start 仅补发尚未告知的（旧版 pi / 无 toolcall_* 事件）。
    if etype in ("tool_call", "tool_execution_start"):
        call_id = str(event.raw.get("toolCallId") or event.raw.get("id") or "")
        if tracker is not None and tracker.tool_call_sent(call_id):
            return []
        args = event.raw.get("args")
        if args is None:
            args = event.raw.get("input") or event.raw.get("arguments")
        if tracker is not None:
            tracker.mark_tool_call(call_id)
        return [
            {
                "type": "tool_call",
                "tool_call_id": call_id,
                "name": _tool_name(event.raw),
                "arguments": args,
            }
        ]
    if etype in ("tool_result", "tool_execution_end"):
        call_id = str(event.raw.get("toolCallId") or event.raw.get("id") or "")
        if tracker is not None and tracker.tool_result_sent(call_id):
            return []
        raw_result = event.raw.get("result")
        if raw_result is None:
            raw_result = event.raw.get("output")
        if tracker is not None:
            tracker.mark_tool_result(call_id)
        return [
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": _tool_name(event.raw),
                "result": _tool_result_text(raw_result)[:_RESULT_PREVIEW_LIMIT],
                "is_error": bool(event.raw.get("isError")),
            }
        ]

    # ── 生命周期 ────────────────────────────────────────────────────────────
    if etype in ("agent_start", "turn_start", "step_start"):
        return [{"type": "activity", "status": "thinking", "agent": agent}]

    if etype == "error":
        return [{"type": "error", "message": str(event.raw.get("message") or "pi 运行错误")}]

    return []


def _translate_message_end(
    raw: dict[str, Any],
    tracker: DeltaTracker | None,
) -> list[dict[str, Any]]:
    """处理 message_end：文本差量 + 工具调用/结果 + usage（可并存，都要发）。"""
    message = raw.get("message")
    if not isinstance(message, dict):
        return []
    role = message.get("role")

    if role == "assistant":
        events: list[dict[str, Any]] = []
        text = _content_text(message)
        if text and tracker is not None:
            chunk = tracker.diff(text)
            if chunk:
                events.append({"type": "delta", "content": chunk})
        # 工具调用已在 toolcall_end 发过（带完整 arguments）。这里只在尚未发过时
        # 补发（旧版 pi / 无 toolcall_* 事件的 provider），避免重复。
        for call in _content_tool_calls(message):
            if tracker is not None and tracker.tool_call_sent(str(call.get("id") or call.get("toolCallId") or "")):
                continue
            events.append(_tool_call_event(call))
        # 文本与工具调用并存时曾只发文本（提前 return 吞掉 tool_call），
        # 前端会看不到工具在执行——两件事都要发。
        # usage 是 pi 的精确计数（Usage.output 等），前端用来收尾展示真实
        # token 数与平均速度（流式期间的实时速度只能估算）。
        #
        # cacheRead / cacheWrite 也要透出：法穿把「AGENTS.md 逐轮字节稳定 →
        # 命中 prompt cache」当核心设计，但改造前账上完全看不到它有没有生效
        # （input_tokens 只装未命中部分）。真机 fixture
        # ``tests/ci/fixtures/agent/*.jsonl`` 实测这两个字段存在（camelCase）。
        # 前端用 cache_hit_rate = cacheRead/(input+cacheRead+cacheWrite) 显示。
        usage = message.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("output"), int | float):
            events.append(
                {
                    "type": "usage",
                    "output_tokens": int(usage["output"]),
                    "input_tokens": int(usage.get("input") or 0),
                    "cache_read_tokens": int(usage.get("cacheRead") or 0),
                    "cache_write_tokens": int(usage.get("cacheWrite") or 0),
                }
            )
        return events

    # 1.4.0 的工具结果消息角色是 toolResult（历史版本用 tool），两种都认。
    # 结果已在 tool_execution_end 发过（带 isError），这里只补发尚未告知的。
    if role in ("toolResult", "tool"):
        call_id = str(message.get("toolCallId") or message.get("id") or "")
        if tracker is not None and tracker.tool_result_sent(call_id):
            return []
        if tracker is not None:
            tracker.mark_tool_result(call_id)
        return [
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": str(message.get("toolName") or ""),
                "result": _content_text(message)[:_RESULT_PREVIEW_LIMIT],
                "is_error": bool(message.get("isError")),
            }
        ]

    return []


def _translate_message_update(
    raw: dict[str, Any],
    tracker: DeltaTracker | None,
) -> list[dict[str, Any]]:
    """处理 message_update（1.4.0 是 delta-only，按分块生命周期翻译）。

    这是正文的唯一来源。要点：

    - ``text_delta`` → delta（并且只把正文计入水位）
    - ``text_end``   → 只做校正：若实际全文比已发多（丢了碎片），补齐差额
    - ``toolcall_*`` → **不得**当正文发；只在 ``toolcall_end`` 发一次完整 tool_call
    - ``thinking_*`` → thinking 事件，不推高正文水位
    """
    events: list[dict[str, Any]] = []
    inner = raw.get("assistantMessageEvent")
    if not isinstance(inner, dict):
        # 非 1.4.0 形态（带 message 快照）：退化为差量
        message = raw.get("message")
        if isinstance(message, dict) and tracker is not None:
            chunk = tracker.diff(_content_text(message))
            if chunk:
                events.append({"type": "delta", "content": chunk})
        return events

    inner_type = inner.get("type")

    if inner_type in {"thinking_delta", "reasoning_delta"}:
        thinking = inner.get("delta") or inner.get("thinking") or ""
        if isinstance(thinking, str) and thinking:
            events.append({"type": "thinking", "content": thinking})
        return events

    if inner_type == "text_delta":
        delta = inner.get("delta")
        if isinstance(delta, str) and delta:
            if tracker is not None:
                tracker.note(delta)
            events.append({"type": "delta", "content": delta})
        return events

    if inner_type == "text_end":
        # 权威全文：只补差额（正常情况已发过，差额为空）
        content = inner.get("content")
        if isinstance(content, str) and tracker is not None:
            chunk = tracker.diff(content)
            if chunk:
                events.append({"type": "delta", "content": chunk})
        return events

    if inner_type == "toolcall_end":
        call = inner.get("toolCall")
        if isinstance(call, dict):
            if tracker is not None:
                tracker.mark_tool_call(str(call.get("id") or call.get("toolCallId") or ""))
            events.append(_tool_call_event(call))
        return events

    # toolcall_delta 是参数 JSON 碎片、toolcall_start 无完整参数，都不能当正文
    return events


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
        for translated in translate_all(event, agent=agent, tracker=tracker):
            yield translated
        if event.kind == "event" and event.event_type == "agent_settled":
            return
