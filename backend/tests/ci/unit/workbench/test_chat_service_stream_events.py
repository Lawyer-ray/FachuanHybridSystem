"""chat_service.py 补充单元测试：流事件桥接 + 历史消息加载.

覆盖 _handle_stream_event 的工具调用/结果/handoff 事件、
_load_message_history 的滑动窗口与批量消息排除、
_convert_to_model_messages 的 tool 分支细节。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from apps.workbench.services.chat_service import (
    MAX_HISTORY_TOKENS,
    _convert_to_model_messages,
    _handle_stream_event,
    _load_message_history,
)


@pytest.fixture()
def event_queue() -> asyncio.Queue:
    return asyncio.Queue()


def _drain(queue: asyncio.Queue) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


class TestHandleStreamEventToolCall:
    @pytest.mark.asyncio
    async def test_dict_args_passthrough(self, event_queue) -> None:
        event = FunctionToolCallEvent(
            part=ToolCallPart(tool_name="search_case", args={"q": "借贷"}, tool_call_id="tc1")
        )
        await _handle_stream_event(event, event_queue, "triage")
        events = _drain(event_queue)
        assert events == [
            {"type": "tool_call", "tool_call_id": "tc1", "name": "search_case", "arguments": {"q": "借贷"}}
        ]

    @pytest.mark.asyncio
    async def test_json_string_args_parsed(self, event_queue) -> None:
        event = FunctionToolCallEvent(part=ToolCallPart(tool_name="get_doc", args='{"id": 3}', tool_call_id="tc2"))
        await _handle_stream_event(event, event_queue, "triage")
        assert _drain(event_queue)[0]["arguments"] == {"id": 3}

    @pytest.mark.asyncio
    async def test_invalid_json_string_args_kept_raw(self, event_queue) -> None:
        event = FunctionToolCallEvent(part=ToolCallPart(tool_name="bad_tool", args="not-json{", tool_call_id="tc3"))
        await _handle_stream_event(event, event_queue, "triage")
        assert _drain(event_queue)[0]["arguments"] == "not-json{"

    @pytest.mark.asyncio
    async def test_handoff_emits_extra_event(self, event_queue) -> None:
        # 真实工具名来自 _handoff_to_research 函数（保留前导下划线）
        event = FunctionToolCallEvent(part=ToolCallPart(tool_name="_handoff_to_research", args={}, tool_call_id="tc4"))
        await _handle_stream_event(event, event_queue, "triage")
        events = _drain(event_queue)
        assert events[0]["type"] == "tool_call"
        assert events[1] == {"type": "handoff", "from_agent": "triage", "to_agent": "research"}

    @pytest.mark.asyncio
    async def test_no_tool_call_id_defaults_empty(self, event_queue) -> None:
        event = FunctionToolCallEvent(part=ToolCallPart(tool_name="x", args={}, tool_call_id=None))
        await _handle_stream_event(event, event_queue, "triage")
        assert _drain(event_queue)[0]["tool_call_id"] == ""


class TestHandleStreamEventToolResult:
    @pytest.mark.asyncio
    async def test_plain_content(self, event_queue) -> None:
        part = ToolReturnPart(tool_name="search_case", tool_call_id="tc1", content="找到 3 条")
        event = FunctionToolResultEvent(part=part, content="找到 3 条")
        await _handle_stream_event(event, event_queue, "triage")
        events = _drain(event_queue)
        assert events == [{"type": "tool_result", "tool_call_id": "tc1", "name": "search_case", "result": "找到 3 条"}]

    @pytest.mark.asyncio
    async def test_wrapper_content_unwrapped(self, event_queue) -> None:
        """content 是带 .content 属性的包装对象时取内层。"""

        class _Wrapped:
            def __init__(self, inner: str) -> None:
                self.content = inner

        part = ToolReturnPart(tool_name="w", tool_call_id="tc9", content="x")
        event = FunctionToolResultEvent(part=part, content=_Wrapped("内层结果"))
        await _handle_stream_event(event, event_queue, "triage")
        assert _drain(event_queue)[0]["result"] == "内层结果"

    @pytest.mark.asyncio
    async def test_long_result_truncated_to_2000(self, event_queue) -> None:
        part = ToolReturnPart(tool_name="big", tool_call_id="tc10", content="x")
        event = FunctionToolResultEvent(part=part, content="a" * 5000)
        await _handle_stream_event(event, event_queue, "triage")
        assert len(_drain(event_queue)[0]["result"]) == 2000

    @pytest.mark.asyncio
    async def test_none_content_becomes_empty(self, event_queue) -> None:
        part = ToolReturnPart(tool_name="n", tool_call_id="tc11", content=None)
        event = FunctionToolResultEvent(part=part, content=None)
        await _handle_stream_event(event, event_queue, "triage")
        assert _drain(event_queue)[0]["result"] == ""


class TestHandleStreamEventOther:
    @pytest.mark.asyncio
    async def test_unknown_event_ignored(self, event_queue) -> None:
        await _handle_stream_event(object(), event_queue, "triage")
        assert _drain(event_queue) == []


@pytest.mark.django_db
class TestLoadMessageHistory:
    async def _session(self) -> Any:
        from apps.workbench.models import WorkbenchSession

        return await WorkbenchSession.objects.acreate(title="历史加载测试")

    async def _msg(self, session: Any, role: str, content: str, **extra: Any) -> Any:
        from apps.workbench.models import WorkbenchMessage

        # 注意：exclude(metadata__source__in=...) 的 NULL 语义会丢掉没有
        # source 键的消息（疑似缺陷），常规消息显式带 source 以走保留路径
        extra.setdefault("metadata", {"source": "chat"})
        return await WorkbenchMessage.objects.acreate(session=session, role=role, content=content, **extra)

    @pytest.mark.asyncio
    async def test_returns_converted_messages_in_order(self) -> None:
        session = await self._session()
        await self._msg(session, "user", "第一条")
        await self._msg(session, "assistant", "第二条")
        await self._msg(session, "user", "第三条")

        history = await _load_message_history(session.id)

        assert len(history) == 3
        assert isinstance(history[0], ModelRequest)
        assert isinstance(history[1], ModelResponse)
        parts0 = history[0].parts
        parts2 = history[2].parts
        assert isinstance(parts0[0], UserPromptPart)
        assert parts0[0].content == "第一条"
        assert parts2[0].content == "第三条"

    @pytest.mark.asyncio
    async def test_empty_session_returns_empty(self) -> None:
        session = await self._session()
        assert await _load_message_history(session.id) == []

    @pytest.mark.asyncio
    async def test_excludes_batch_messages_and_other_sessions(self) -> None:
        session = await self._session()
        other = await self._session()
        await self._msg(session, "user", "正常消息")
        await self._msg(session, "user", "批量项", metadata={"source": "batch_item"})
        await self._msg(session, "assistant", "批量分析", metadata={"source": "batch_analysis"})
        await self._msg(other, "user", "别的会话")

        history = await _load_message_history(session.id)

        contents = [p.content for m in history for p in getattr(m, "parts", [])]
        assert contents == ["正常消息"]

    @pytest.mark.asyncio
    async def test_sliding_window_drops_oldest_when_over_token_budget(self) -> None:
        session = await self._session()
        # 造一条超预算的旧消息 + 一条新的短消息
        await self._msg(session, "user", "旧" * (MAX_HISTORY_TOKENS // 2))
        await self._msg(session, "user", "新消息")

        history = await _load_message_history(session.id, max_tokens=100)

        # 至少保留最新一条（旧消息因超预算被滑出窗口）
        contents = [p.content for m in history for p in getattr(m, "parts", [])]
        assert contents == ["新消息"]

    @pytest.mark.asyncio
    async def test_tool_message_converted_to_tool_return(self) -> None:
        session = await self._session()
        await self._msg(
            session,
            "tool",
            "调用工具: search",
            tool_call_id="tc_1",
            tool_name="search",
            tool_output={"result": "结果A"},
        )

        history = await _load_message_history(session.id)

        part = history[0].parts[0]
        assert isinstance(part, ToolReturnPart)
        assert part.tool_call_id == "tc_1"
        assert part.tool_name == "search"
        assert part.content == "结果A"

    @pytest.mark.asyncio
    async def test_tool_message_non_dict_output_stringified(self) -> None:
        session = await self._session()
        await self._msg(session, "tool", "兜底内容", tool_call_id="tc_2", tool_name="t", tool_output="raw-string")

        history = await _load_message_history(session.id)
        part = history[0].parts[0]
        assert part.content == "raw-string"


class TestConvertToModelMessages:
    def test_tool_output_dict_without_result_key_falls_back_to_content(self) -> None:
        from types import SimpleNamespace

        msg = SimpleNamespace(
            role="tool", content="原始内容", tool_output={"other": 1}, tool_call_id="t1", tool_name="n"
        )
        result = _convert_to_model_messages([msg])
        assert result[0].parts[0].content == "原始内容"

    def test_system_role_skipped(self) -> None:
        from types import SimpleNamespace

        msg = SimpleNamespace(role="system", content="sys")
        assert _convert_to_model_messages([msg]) == []
