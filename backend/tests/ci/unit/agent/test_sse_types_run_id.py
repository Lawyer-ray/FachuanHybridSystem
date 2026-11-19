"""SSE 事件契约的 ``run_id`` 字段（多 agent 并行的寻址维度）。

同一会话可并行多个 agent，前端靠 ``run_id`` 把事件挂到正确的栏；审批卡片尤其
关键——挂错栏等于让人批错 agent 的写操作。

同时守护「运行产出事件一律带 run_id」这条契约：往
``AgentStreamEvent`` 加新事件类时若忘了 run_id，并行场景下该事件就会
掉进「不知道属于谁」的灰色地带。空串缺省保证旧数据 / 未接入的调用方不断流。
"""

from __future__ import annotations

import pytest

from apps.agent.sse_types import (
    ActivityEvent,
    AgentStreamEvent,
    ApprovalRequestEvent,
    CompactionEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    QuestionRequestEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
    generate_ts,
)

# 每个事件类最小的必填载荷（只补必填字段，run_id 走缺省值）
_MINIMAL_PAYLOADS: list[tuple[type, dict[str, object]]] = [
    (MetaEvent, {"type": "meta", "session_id": "s-1"}),
    (ActivityEvent, {"type": "activity", "status": "thinking"}),
    (DeltaEvent, {"type": "delta", "content": "hi"}),
    (ThinkingEvent, {"type": "thinking", "content": "hmm"}),
    (ToolCallEvent, {"type": "tool_call", "tool_call_id": "tc-1", "name": "mcp__fachuan__x"}),
    (ToolResultEvent, {"type": "tool_result", "tool_call_id": "tc-1", "name": "mcp__fachuan__x"}),
    (
        ApprovalRequestEvent,
        {"type": "approval_request", "approval_id": "ap-1", "tool_name": "mcp__fachuan__delete_case"},
    ),
    (UsageEvent, {"type": "usage", "output_tokens": 10}),
    (QuestionRequestEvent, {"type": "question_request", "question_id": "q-1"}),
    (CompactionEvent, {"type": "compaction", "phase": "start"}),
    (ErrorEvent, {"type": "error", "message": "boom"}),
    (DoneEvent, {"type": "done", "session_id": "s-1"}),
]


@pytest.mark.parametrize(("model", "payload"), _MINIMAL_PAYLOADS, ids=[m.__name__ for m, _ in _MINIMAL_PAYLOADS])
def test_run_id_defaults_to_empty_string(model: type, payload: dict[str, object]) -> None:
    """缺省为空串：旧前端 / 旧数据读不到 run_id 也不断流。"""
    event = model.model_validate(payload)  # type: ignore[attr-defined]
    assert event.run_id == ""
    assert event.model_dump()["run_id"] == ""


@pytest.mark.parametrize(("model", "payload"), _MINIMAL_PAYLOADS, ids=[m.__name__ for m, _ in _MINIMAL_PAYLOADS])
def test_run_id_round_trips_through_serialization(model: type, payload: dict[str, object]) -> None:
    run_id = "abc-123:pi:1"
    event = model.model_validate({**payload, "run_id": run_id})  # type: ignore[attr-defined]
    assert event.run_id == run_id
    assert event.model_dump()["run_id"] == run_id
    # JSON 往返（SSE 帧实际走的是这条路）
    assert event.model_dump_json().find(f'"run_id":"{run_id}"') >= 0


def test_generated_ts_exposes_run_id_on_every_event() -> None:
    """TS 生成物必须逐类带 ``run_id?: string`` 与 ``agent?: string``。

    断言刻意**不依赖模板排版**：生成器已从手写字符串改成 ``model_fields`` 反射，
    排版本来就会随字段增删变化；钉住排版等于把测试变成模板的第二个副本（历史
    上正是这样：模板与测试一起漂移，而运行时第三个样子）。
    """
    from apps.agent.sse_types import EVENT_MODELS
    from apps.agent.sse_types import generate_ts as _gen

    ts = generate_ts()
    total = len(EVENT_MODELS)
    # 每个事件类各出现一次 run_id / agent；多一个说明有分支漏声明，少一个说明生成器漏类
    assert ts.count("run_id?: string") == total
    assert ts.count("agent?: string") == total
    # 每个事件类型都出现在生成物里
    for model in EVENT_MODELS:
        tag = model.model_fields["type"].annotation.__args__[0]  # type: ignore[attr-defined]
        assert f"type: '{tag}'" in ts, f"生成物缺少事件 {tag}"
    assert _gen() == ts


def test_stream_event_union_covers_all_run_scoped_models() -> None:
    """联合类型必须包含全部带 run_id 的事件类（漏加 = 该事件在前端不可见）。"""
    union_args = set(AgentStreamEvent.__args__)  # type: ignore[attr-defined]
    assert {model for model, _ in _MINIMAL_PAYLOADS} <= union_args
