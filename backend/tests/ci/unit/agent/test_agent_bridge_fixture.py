"""pi 1.4.0 真实事件流驱动的事件翻译测试。

fixture 来自真机录制（``pi --mode json``，1.4.0），已脱敏：

- ``pi140_text_only.jsonl``：纯文本一轮
- ``pi140_with_tool.jsonl``：带一次工具调用（read）与工具结果

为什么要真实 fixture：上游 1.4.0 把 ``message_update`` 改成 delta-only，
新增 ``text_end`` / ``toolcall_*`` 一整套分块事件；手写合成事件永远造不出
「usage 只在 text_end 有值」「工具结果角色叫 toolResult」这类真实细节，
而 bridge.py 的假设正是踩在这些细节上。合成事件全绿 + 真机丢字，就是这么来的。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.agent.pi.bridge import DeltaTracker, translate_all
from apps.agent.pi.rpc_client import PiEvent

#: 文件位于 backend/tests/ci/unit/agent/，向上四层即 backend/，再进 tests/ci/fixtures
FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests" / "ci" / "fixtures" / "agent"


def _load(name: str) -> list[dict[str, Any]]:
    path = FIXTURE_DIR / name
    assert path.exists(), f"缺少 fixture: {path}"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _translate_all(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """跑完整条流，返回（事件列表，拼起来的正文）。"""
    tracker = DeltaTracker()
    events: list[dict[str, Any]] = []
    for record in records:
        events.extend(translate_all(PiEvent("event", record), tracker=tracker))
    text = "".join(str(e.get("content") or "") for e in events if e.get("type") == "delta")
    return events, text


class TestTextOnlyFixture:
    def test_text_reconstructed_exactly(self) -> None:
        """把 delta 拼起来必须等于模型的完整回答（不丢字、不重复）。"""
        _, text = _translate_all(_load("pi140_text_only.jsonl"))
        assert text == "联调成功"

    def test_no_duplicate_delta(self) -> None:
        """text_end 带权威全文，不得再当增量重发一遍。"""
        events, _ = _translate_all(_load("pi140_text_only.jsonl"))
        deltas = [e["content"] for e in events if e.get("type") == "delta"]
        assert deltas == ["联", "调成功"]

    def test_usage_emitted_once_with_real_counts(self) -> None:
        events, _ = _translate_all(_load("pi140_text_only.jsonl"))
        usage = [e for e in events if e.get("type") == "usage"]
        assert len(usage) == 1
        assert usage[0]["output_tokens"] == 4
        assert usage[0]["input_tokens"] == 486


class TestToolCallFixture:
    def test_tool_call_once_with_arguments(self) -> None:
        """toolcall_end 与 tool_execution_start 是同一调用，只能发一次且带参数。"""
        events, _ = _translate_all(_load("pi140_with_tool.jsonl"))
        calls = [e for e in events if e.get("type") == "tool_call"]
        assert len(calls) == 1
        assert calls[0]["name"] == "read"
        assert calls[0]["arguments"] == {"path": "note.txt"}

    def test_tool_result_once_as_plain_text(self) -> None:
        """结果在 tool_execution_end 里是 dict，必须取 content 文本而不是 Python repr。"""
        events, _ = _translate_all(_load("pi140_with_tool.jsonl"))
        results = [e for e in events if e.get("type") == "tool_result"]
        assert len(results) == 1
        assert results[0]["result"] == "hello-content\n"
        assert "{'content'" not in results[0]["result"]

    def test_tool_argument_json_never_leaks_into_text(self) -> None:
        """回归：toolcall_delta 是参数 JSON 片段，曾混进用户看到的回答。"""
        _, text = _translate_all(_load("pi140_with_tool.jsonl"))
        assert '{"path"' not in text
        assert text.startswith("我先读取该文件。")

    def test_full_answer_after_tool_loop(self) -> None:
        """工具循环后的第二轮回答必须完整到达（不得被水位吞掉）。"""
        _, text = _translate_all(_load("pi140_with_tool.jsonl"))
        assert text.endswith("hello-content\n```")

    def test_thinking_events_absent_when_not_thinking(self) -> None:
        events, _ = _translate_all(_load("pi140_with_tool.jsonl"))
        assert not [e for e in events if e.get("type") == "thinking"]

    def test_no_unknown_event_types_leak(self) -> None:
        """只允许契约内的事件类型出现（防止内部诊断泄漏给浏览器）。"""
        allowed = {"activity", "delta", "thinking", "tool_call", "tool_result", "usage", "error"}
        events, _ = _translate_all(_load("pi140_with_tool.jsonl"))
        assert {e["type"] for e in events} <= allowed
