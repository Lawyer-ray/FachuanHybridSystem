"""UI 动作下发（T1 单向通道）的返回值契约。

为什么这些断言值得写：**返回值就是模型能拿到的全部信息**。

- ``no_channel`` 被写成 ``dispatched`` → 模型会对律师说「已切到待处理」，页面根本没动；
- ``invalid_args`` 被吞成异常 → 模型只能拿同一个错参数重试到死（它看不到哪一字段错）；
- ``dry`` / ``off`` 漏掉 → 灰度观察期与一键回滚形同虚设。

还有一条结构性断言：**下发绝不阻塞**。这是本通道与 ``ask_user`` 的唯一本质差别
（后者要答案、要登记等待器；动作只是手势）。用 ``asyncio.wait_for`` 加一个远小于任何
超时的时间上限来钉它——一旦有人给这里加上 "等一下前端回执"，本用例会先超时。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from apps.agent.services.ui_action import publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction

NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")
SET_STAGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_set_stage")


class _FakeBus:
    """记录发布内容的最小假总线。

    只实现 ``publish_ui_action`` 真正调用的三个方法：多实现一个方法就等于在测试里
    养一份会跟着真实总线漂移的假货，而这里要钉的是**本模块的调用口径**，不是总线。
    """

    def __init__(self, *, local: bool = True, delivered: int = 1, remote: int = 0) -> None:
        self.local = local
        self.delivered = delivered
        self.remote = remote
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def has_subscribers(self, session_id: str) -> bool:
        return self.local

    async def remote_subscriber_count(self, session_id: str) -> int:
        return self.remote

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        self.published.append((session_id, event))
        return self.delivered


def _install_bus(monkeypatch: pytest.MonkeyPatch, bus: _FakeBus) -> _FakeBus:
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认走 ``on``：本机 shell 里若导出过 ``FACHUAN_UI_ACTION``，用例会随环境变色。"""
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)


def _session_id() -> str:
    """每个用例独立的会话 id。

    ``sequence`` 是按会话计的进程内计数，跨用例共用同一个 id 会让断言依赖执行顺序。
    """
    return f"ui-action-{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_no_channel_without_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有会话 = 不可能有 SSE 通道：立即 ``no_channel``，且**不要**去碰总线。"""

    class _ExplodingBus(_FakeBus):
        async def has_subscribers(self, session_id: str) -> bool:
            raise AssertionError("session_id 为空时不该判活")

        async def publish(self, session_id: str, event: dict[str, Any]) -> int:
            raise AssertionError("session_id 为空时不该发布")

    _install_bus(monkeypatch, _ExplodingBus())

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=None)

    assert result["status"] == "no_channel"
    assert result["delivered"] is False
    assert "不要假定页面已变化" in result["note"]


@pytest.mark.asyncio
async def test_invalid_args_returns_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """参数不合法要回给模型**具体字段**（它据此改参数），而不是抛异常。"""
    bus = _install_bus(monkeypatch, _FakeBus())

    missing = await publish_ui_action(action=NAVIGATE, arguments={}, session_id=_session_id())
    assert missing["status"] == "invalid_args"
    assert "path" in missing["error"]

    unknown = await publish_ui_action(
        action=SET_STAGE,
        arguments={"stage": "todo", "until": "明天"},
        session_id=_session_id(),
    )
    assert unknown["status"] == "invalid_args"
    assert "until" in unknown["error"]

    bad_enum = await publish_ui_action(action=SET_STAGE, arguments={"stage": "filed_done"}, session_id=_session_id())
    assert bad_enum["status"] == "invalid_args"
    assert "filed_done" in bad_enum["error"]

    assert bus.published == [], "参数非法时绝不发布（否则前端还得再挡一次脏参数）"


@pytest.mark.asyncio
async def test_off_mode_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    """``off`` 是一键回滚：不下发、不判活，且明确告诉模型页面不会变。"""
    bus = _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv("FACHUAN_UI_ACTION", "off")

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=_session_id())

    assert result["status"] == "disabled"
    assert result["delivered"] is False
    assert bus.published == []


@pytest.mark.asyncio
async def test_dry_mode_logs_without_publish(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """``dry`` 是灰度观察：只记日志，页面零变化——所以状态不能叫 ``dispatched``。"""
    bus = _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv("FACHUAN_UI_ACTION", "dry")
    caplog.set_level("INFO", logger="apps.agent.services.ui_action")

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=_session_id())

    assert result["status"] == "dry_run"
    assert result["delivered"] is False
    assert bus.published == []
    assert any("ui_action dispatch" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_dispatched_publishes_contract_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常下发：事件字段齐全、``observed=False``，且**不等前端**。"""
    bus = _install_bus(monkeypatch, _FakeBus())
    session_id = _session_id()

    # 0.5s 远小于任何真实超时（审批 120s / 提问 180s）：如果这段代码开始等回执，这里先红。
    result = await asyncio.wait_for(
        publish_ui_action(action=SET_STAGE, arguments={"stage": "done"}, session_id=session_id),
        timeout=0.5,
    )

    assert result["status"] == "dispatched"
    assert result["delivered"] is True
    assert result["observed"] is False, "执行结果不回传，模型不该被允许断言页面已经变成什么样"
    assert "不要断言" in result["note"]
    assert len(result["call_id"]) == 32

    assert len(bus.published) == 1
    published_session, event = bus.published[0]
    assert published_session == session_id
    assert event["type"] == "ui_action"
    assert event["call_id"] == result["call_id"]
    assert event["action"] == "ui_material_prep_set_stage"
    assert event["arguments"] == {"stage": "done"}
    assert event["route"] == "/material-prep"
    assert event["sequence"] == 1

    # 同一会话的第二次动作序号递增（前端靠它发现跳号；不重排）
    second = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=session_id)
    assert second["status"] == "dispatched"
    assert bus.published[1][1]["sequence"] == 2
    assert bus.published[1][1]["route"] is None


@pytest.mark.asyncio
async def test_delivered_false_when_nobody_listens(monkeypatch: pytest.MonkeyPatch) -> None:
    """有会话但没人订阅：状态仍是 ``dispatched``，只是 ``delivered=False``。

    为什么不报 ``no_channel``：配了 Redis 时事件已进回放流（TTL 300s），律师在重连窗口内
    打开页面仍可能执行它——这时断言「没人收到」反而是错的。真正的事实是「没确认送达」。
    """
    bus = _install_bus(monkeypatch, _FakeBus(local=False, delivered=0, remote=0))

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=_session_id())

    assert result["status"] == "dispatched"
    assert result["delivered"] is False
    assert len(bus.published) == 1
