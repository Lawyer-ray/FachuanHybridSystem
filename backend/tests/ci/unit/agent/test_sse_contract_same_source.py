"""SSE 契约同源守卫。

为什么需要它：契约历史上其实有**三个**源——

1. `apps/agent/sse_types.py` 的 pydantic 模型；
2. 同文件里手抄的 `generate_ts()` 模板字符串；
3. 真正发事件的运行时（`stream.py` / `multi.py` / 各 `*_backend.py`）。

三者各自漂移，而生成物永远「看起来是对的」：重生成只是把模板再抄一遍，漂移
一条不少。2026-11 的实测就是如此——模板与 pydantic 逐字段一致（差集为 ∅），
但两者**一起**落后于运行时：`multi.py` 每条中间帧都在补 `agent` / `agents` /
`reason`，契约里一个都没有。

所以本文件守住两件事，缺一不可：

- `test_ts_matches_checked_in_file`：生成物与仓库里的 `sse-events.ts` 逐字节一致。
  挡住「改了 pydantic 忘了重生成」和「手改生成物」。
- `test_every_event_declares_agent`：每个事件类都声明 `agent`。挡住运行时漂移里
  最要命的那一类——「这帧是谁发的」在多栏并答时是分流到哪一栏的唯一依据，
  它不在类型里就只能靠前端属性探测（`domain/dual.ts` 的 `agentOf`）。

注意本文件**不建库**（无 `django_db`）；只 import 类型模块。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.agent.sse_types import AgentStreamEvent  # 导入即校验联合类型可构造
from apps.agent.sse_types import EVENT_MODELS, WIRE_UNREACHABLE, DoneEvent, generate_ts

#: 仓库内生成物的位置（本文件在 backend/tests/ci/unit/agent/，上推 5 层到仓库根）
_TS_PATH = Path(__file__).resolve().parents[5] / "frontend" / "src" / "features" / "copilot" / "sse-events.ts"


def test_ts_matches_checked_in_file() -> None:
    """生成物必须与仓库里的 `sse-events.ts` 逐字节一致。

    失败时的修法只有一条：改 `sse_types.py` 后重跑
    `python -m apps.agent.sse_types --ts > frontend/src/features/copilot/sse-events.ts`。
    **不要**手改生成物，也不要为了让断言变绿去改断言。
    """
    assert _TS_PATH.exists(), f"找不到契约生成物：{_TS_PATH}"

    generated = generate_ts()
    checked_in = _TS_PATH.read_text(encoding="utf-8")

    if generated != checked_in:
        import difflib

        diff = "\n".join(
            difflib.unified_diff(
                checked_in.splitlines(),
                generated.splitlines(),
                fromfile="仓库里的 sse-events.ts",
                tofile="由 sse_types.py 生成的结果",
                lineterm="",
            )
        )
        pytest.fail(
            "SSE 契约与生成物不一致（改了 sse_types.py 却没重生成？）。\n"
            "修法：python -m apps.agent.sse_types --ts > "
            "frontend/src/features/copilot/sse-events.ts\n\n" + diff
        )


@pytest.mark.parametrize("model", EVENT_MODELS, ids=lambda m: m.__name__)
def test_every_event_declares_agent(model: type) -> None:
    """每个事件都必须声明 `agent`（「这帧是谁发的」）。

    例外为零：连编排层代发的 `meta` / `activity` / `done` 也带——多栏并答时
    它们同样要归栏，否则前端要靠 `agents` 反推，而 `agents` 在单栏轮次里是空的。
    """
    fields = getattr(model, "model_fields", {})
    assert "agent" in fields, (
        f"{model.__name__} 没有声明 agent：多栏并答时前端无法把这帧挂到正确的栏。"
        "请在模型上加 `run_id` / `agent`（可从 _RunScoped 继承）。"
    )
    assert "run_id" in fields, f"{model.__name__} 没有声明 run_id：并发运行的事件无法按运行归集。请继承 _RunScoped。"


def test_done_finish_reason_reachability() -> None:
    """`done.finish_reason` 的可达集合必须是「枚举减去线上不可达」。

    历史事故：前端按一套枚举等 `error`，后端永远发 `ok`，于是「降级」在界面上
    与「正常结束」不可区分。现在把可达性写成断言，改枚举的人必须先改这里。
    """
    annotation = DoneEvent.model_fields["finish_reason"].annotation
    declared = set(getattr(annotation, "__args__", ()))
    assert declared == {"ok", "degraded", "error", "cancelled"}
    assert frozenset({"cancelled"}) == WIRE_UNREACHABLE
    # 线上可达 = 声明的枚举 - 不可达
    wire_reachable = declared - set(WIRE_UNREACHABLE)
    assert wire_reachable == {"ok", "degraded", "error"}


def test_generator_covers_every_event_model() -> None:
    """生成器必须覆盖全部事件类（漏一个 = 那个事件在前端是未知类型，静默丢弃）。"""
    ts = generate_ts()
    for model in EVENT_MODELS:
        name = model.model_fields["type"].annotation
        literal = getattr(name, "__args__", ())
        assert literal, f"{model.__name__}.type 不是 Literal"
        assert f"type: '{literal[0]}'" in ts, f"生成物里缺少 {literal[0]} 事件"
