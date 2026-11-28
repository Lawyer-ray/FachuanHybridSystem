"""``ui_action_batch`` 的整批校验与批量下发（v2-C）。

为什么这些断言值得写：批量把「N 张审批卡」压成「1 张」，代价是**一次确认背后可能有多步**。
所以只有两件事不能错：

- **整批拒绝**：混进一条坏步骤就发出去前几条，律师看到的是「一半动了」，而模型手里只有
  一个空回执——既不知道从哪一步重来，也不知道页面停在哪。所以任何一条不合法都必须
  **零发布**（``bus.published == []``），而不是「跳过坏的、把好的照发」。
- **批次身份与顺序**：前端靠 ``batch_id`` / ``batch_index`` 串行执行。序号错一次就是
  「先切 stage 再跳页」被换成「先跳页再切 stage」，而这件事不会报错。

另外钉两条成本线：只有第一步等回执（五步各等 2s = 10s，都发生在模型循环内部），
以及第一条就没通道时后面的步骤一条都不发。

回执等待的语义在 ``test_ui_action_ack.py``，单条下发契约在 ``test_ui_action_publish.py``；
本文件只管批量这一层。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.agent.services.ui_action import ack
from apps.agent.services.ui_action.batch import BATCH_TOOL_NAME, MAX_BATCH_STEPS, BatchInvalid, publish_batch


class _FakeBus:
    """记录发布内容的最小假总线（口径同 ``test_ui_action_publish._FakeBus``）。"""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def has_subscribers(self, session_id: str) -> bool:
        return True

    async def remote_subscriber_count(self, session_id: str) -> int:
        return 0

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        self.published.append((session_id, event))
        return 1


def _install_bus(monkeypatch: pytest.MonkeyPatch) -> _FakeBus:
    bus = _FakeBus()
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认 ``on`` 且关掉回执窗口：本文件钓的是「整批怎么校验、帧长什么样」。

    回执窗口关掉后每一步都立刻返回（走 pending 分支），用例不会白等 2s；
    进程内积压表也要清空，否则上一个用例的 pending 会以 ``earlier_results`` 混进来。
    """
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0")
    ack._PENDING.clear()


def _session_id() -> str:
    """每用例独立会话 id（``sequence`` 是按会话计的进程内计数，共用会让断言依赖执行顺序）。"""
    return f"ui-batch-{uuid.uuid4().hex}"


def _steps() -> list[dict[str, Any]]:
    """一批合法的三步：跳页 → 切 stage → 开面板（三档都在清单里）。"""
    return [
        {"action": "ui_navigate", "args": {"path": "/material-prep?stage=todo"}},
        {"action": "ui_material_prep_set_stage", "args": {"stage": "todo"}},
        {"action": "ui_copilot_open", "args": {}},
    ]


def test_batch_invalid_is_value_error_so_mcp_returns_iserror() -> None:
    """整批拒绝必须真的变成 ``isError``：``server._t`` 只翻译 ``ValueError``。

    换成别的基类时 SDK 会把它包成 ``Error executing tool ui_action_batch``（原因被丢掉）
    ——模型只看到「失败了」，而它需要的是「第几步、错在哪」，那正是本 lane 的拒绝文案存在的意义。
    """
    assert issubclass(BatchInvalid, ValueError)


@pytest.mark.asyncio
async def test_three_steps_publish_in_order_with_batch_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """① 合法三步按序下发，且每帧自带同一个 batch_id 与递增 batch_index。"""
    bus = _install_bus(monkeypatch)
    steps = _steps()

    result = await publish_batch(steps=steps, session_id=_session_id(), note="切材料页再开面板")

    assert result["status"] == "dispatched"
    assert [step["index"] for step in result["steps"]] == [0, 1, 2]
    assert [step["action"] for step in result["steps"]] == [step["action"] for step in steps]

    events = [event for _session, event in bus.published]
    assert [event["action"] for event in events] == [step["action"] for step in steps], "必须按 steps 的顺序下发"
    assert [event["batch_index"] for event in events] == [0, 1, 2]
    assert {event["batch_id"] for event in events} == {result["batch_id"]}, "同一批共用一个 batch_id"
    # 返回值里的 call_id 必须就是帧里的那个：模型靠它去 ui_action_results 对账
    assert [event["call_id"] for event in events] == [step["call_id"] for step in result["steps"]]

    # 第一步的完整返回值原样带在 observed 里（窗口关了 → observed=False + pending）
    assert result["observed"]["call_id"] == result["steps"][0]["call_id"]
    assert result["observed"]["observed"] is False
    assert result["observed"]["pending"] is True
    # 中间步骤的回执不会因为「下一步的下发顺手 drain 了一次」而消失
    assert any("ui_navigate" in item for item in result.get("earlier_results") or [])


@pytest.mark.asyncio
async def test_more_than_five_steps_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """② 超过 5 步整批拒绝：拒绝文案要说清「几步、上限几」——模型据此拆批。"""
    bus = _install_bus(monkeypatch)
    steps = [{"action": "ui_navigate", "args": {"path": f"/p{i}"}} for i in range(MAX_BATCH_STEPS + 1)]

    with pytest.raises(BatchInvalid) as excinfo:
        await publish_batch(steps=steps, session_id=_session_id())

    message = str(excinfo.value)
    assert f"最多 {MAX_BATCH_STEPS} 步" in message
    assert f"这次给了 {MAX_BATCH_STEPS + 1} 步" in message
    assert bus.published == [], "超限时绝不发布"


@pytest.mark.asyncio
async def test_unknown_action_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """③ 含清单外动作整批拒绝：文案要指出第几步、并列出可用动作。"""
    bus = _install_bus(monkeypatch)
    steps = _steps()[:1] + [{"action": "ui_teleport", "args": {}}]

    with pytest.raises(BatchInvalid) as excinfo:
        await publish_batch(steps=steps, session_id=_session_id())

    message = str(excinfo.value)
    assert "第 2 步" in message
    assert "ui_teleport" in message
    assert "ui_navigate" in message, "可用动作要列出来，模型才知道能改成什么"
    assert bus.published == []


@pytest.mark.asyncio
async def test_nested_batch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """④ 嵌套批量整批拒绝：一张卡里再套一张卡，审批卡就没法读了。"""
    bus = _install_bus(monkeypatch)
    steps = _steps()[:1] + [{"action": BATCH_TOOL_NAME, "args": {"steps": _steps()}}]

    with pytest.raises(BatchInvalid) as excinfo:
        await publish_batch(steps=steps, session_id=_session_id())

    message = str(excinfo.value)
    assert "第 2 步" in message
    assert "不能嵌套" in message
    assert bus.published == []


@pytest.mark.asyncio
async def test_any_invalid_args_rejects_whole_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑤ 任一条 args 非法 → **整批零发布**（不做「能跑几条跑几条」）。"""
    bus = _install_bus(monkeypatch)
    steps = _steps()[:1] + [{"action": "ui_material_prep_set_stage", "args": {"stage": "filed_done"}}]

    with pytest.raises(BatchInvalid) as excinfo:
        await publish_batch(steps=steps, session_id=_session_id())

    message = str(excinfo.value)
    assert "第 2 步" in message
    assert "filed_done" in message, "非法值要原样回给模型（它才知道自己写了什么）"
    assert bus.published == [], "有一条不合法就整批零发布，连第 1 步都不能发"


@pytest.mark.asyncio
async def test_first_step_without_channel_stops_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一步就没通道（``no_channel``）：后面的步骤一条都不发，状态原样交给模型。"""
    bus = _install_bus(monkeypatch)
    steps = _steps()

    result = await publish_batch(steps=steps, session_id=None)

    assert result["status"] == "no_channel"
    assert result["steps"] == [], "没有通道就没有可回报的 call_id"
    assert result["observed"]["status"] == "no_channel"
    assert bus.published == [], "没通道时连总线都不该碰"


@pytest.mark.asyncio
async def test_only_first_step_waits_for_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    """只有第一步登记回执等待者：五步各等 2s 会把一次交互拖成「卡住了」。

    判据用「登记了几次等待者」而不是墙钟：前者是确定性的，后者在 CI 上会飘。
    """
    _install_bus(monkeypatch)
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0.01")
    registered: list[str] = []
    original_register = ack.register

    async def _counting_register(call_id: str):
        registered.append(call_id)
        return await original_register(call_id)

    monkeypatch.setattr(ack, "register", _counting_register)

    result = await publish_batch(steps=_steps(), session_id=_session_id())

    assert result["status"] == "dispatched"
    assert registered == [result["steps"][0]["call_id"]], "只有第一步等回执，其余立刻返回"
