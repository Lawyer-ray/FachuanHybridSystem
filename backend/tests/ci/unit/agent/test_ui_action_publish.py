"""UI 动作下发（T1 单向通道）的返回值契约。

为什么这些断言值得写：**返回值就是模型能拿到的全部信息**。

- ``no_channel`` 被写成 ``dispatched`` → 模型会对律师说「已切到待处理」，页面根本没动；
- ``invalid_args`` 被吞成异常 → 模型只能拿同一个错参数重试到死（它看不到哪一字段错）；
- ``dry`` / ``off`` 漏掉 → 灰度观察期与一键回滚形同虚设。

还有一条结构性断言：**回执窗口关掉时下发绝不阻塞**（``FACHUAN_UI_ACTION_ACK_WAIT=0``）。
等回执是 v2-A 才有的能力（默认窗口 2s），但窗口必须能被运维关掉——灰度、弱网、
或确信没人看页面时，一个动作不该白占 2s 的 pi 执行位。用远小于任何超时的上限来钉它：
一旦这个分支开始无条件等待，本用例会先超时。

回执本身的语义（幂等/超时/积压）在 ``test_ui_action_ack.py``，本文件只管下发契约。

最后五组用例钓「服务端幂等」：同一会话 + 同一 ``confirm`` 动作 + 同一参数还在飞（台账里
仍是 ``outcome="unknown"``）时，第二次下发必须返回 ``duplicate`` 而不是再发一帧——模型
没在 2s 窗口里拿到回执时会原样重发，而前端的 5s 同参窗只管同一标签页。判据不是「出去
前查一眼台账」（两个 worker 同时下发时两边都会查空），而是台账那条部分唯一索引
（见 ``test_ui_action_audit.py`` ⑥）：占位插不进去就是重复。这批用例必须建库，
``django_db(transaction=True)`` 的理由同 ``test_ui_action_audit.py``：async ORM 在 asgiref
执行器连接上跑，普通事务包裹下看不见用例里创建的行。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from apps.agent.models import AgentSession, AgentUiAction
from apps.agent.services.ui_action import ack, publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from apps.organization.models import Lawyer

NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")
SET_STAGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_set_stage")
#: 清单里唯一的 ``confirm`` 动作：服务端幂等（占位）只对需要审计的档生效。
JUDGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_judge")


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
    """默认走 ``on`` 且关掉回执窗口。

    - ``FACHUAN_UI_ACTION``：本机 shell 里若导出过开关，用例会随环境变色；
    - ``FACHUAN_UI_ACTION_ACK_WAIT=0``：本文件钓的是**下发契约**（事件字段、模式开关），
      回执等待的语义在 ``test_ui_action_ack.py``；不关窗口每条用例都要白等 2s。

    同时清空进程内积压表：没等到回执的动作会被登记进去，跨用例残留会让
    ``earlier_results`` 随机出现在后面用例的返回值里。
    """
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0")
    ack._PENDING.clear()


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
    """正常下发：事件字段齐全、``observed=False``（窗口已关 → 直接走积压），且**不等前端**。"""
    bus = _install_bus(monkeypatch, _FakeBus())
    session_id = _session_id()

    # 0.5s 远小于任何真实超时（审批 120s / 提问 180s）：如果这段代码开始等回执，这里先红。
    result = await asyncio.wait_for(
        publish_ui_action(action=SET_STAGE, arguments={"stage": "done"}, session_id=session_id),
        timeout=0.5,
    )

    assert result["status"] == "dispatched"
    assert result["delivered"] is True
    assert result["observed"] is False, "没拿到回执就不该允许模型断言页面已经变成什么样"
    assert result["pending"] is True
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


# ── 服务端幂等：占位（部分唯一索引）挡住同键的第二条在飞 ─────────────────


async def _make_session(username: str) -> AgentSession:
    """建真会话：只有 ``session_id`` 是真 UUID，台账行才会挂到会话上（占位的键含会话）。

    不设口令：本文件不测登录，任何口令字面量都会被 detect-secrets 拦。
    """
    user: Lawyer = await Lawyer.objects.acreate(username=username, real_name=f"下发去重用例-{username}")
    return await AgentSession.objects.acreate(title="下发去重用例", user=user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_same_confirm_action_twice_is_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑦ 同一会话 + 同一 confirm 动作 + 同参数连发两次：第二次 ``duplicate``，总线只多一帧。

    返回里必须带**第一次**的 ``call_id``：模型下一步是去取那一次的结果
    （``ui_action_results``），而不是再发一遍、把同一个写动作做两次。
    """
    session = await _make_session("uidispatch-dup")
    bus = _install_bus(monkeypatch, _FakeBus())
    args = {"packId": 814, "target": "done"}
    session_id = str(session.session_id)

    first = await publish_ui_action(action=JUDGE, arguments=args, session_id=session_id)
    second = await publish_ui_action(action=JUDGE, arguments=args, session_id=session_id)

    assert first["status"] == "dispatched"
    assert second["status"] == "duplicate"
    assert second["call_id"] == first["call_id"], "要交回那一次的 call_id，模型才知道去取谁"
    assert second["delivered"] is False
    assert "ui_action_results" in second["note"] and "不要原样重发" in second["note"]
    assert "仍在执行中" in second["note"], "文案要能区分「在飞」与「已经做过」"
    assert len(bus.published) == 1, "被去重的那次一帧都不该发"
    # 占位行只有一条：第二次连「照抄一行再标重复」都不该发生（它会撞约束）。
    assert await AgentUiAction.objects.acount() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_settled_action_can_be_dispatched_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑧ 第一次结算（``outcome`` 落成 ``ok``）之后，同参数第三次正常下发。

    约束的条件是 ``outcome="unknown"``：已有结局的行不许拦住下一次——否则「同一个材料包
    先判 done、律师改主意再判 filed」会被当成重复挡掉，而它是一次新的决定。
    """
    session = await _make_session("uidispatch-settled")
    bus = _install_bus(monkeypatch, _FakeBus())
    args = {"packId": 814, "target": "done"}
    session_id = str(session.session_id)

    first = await publish_ui_action(action=JUDGE, arguments=args, session_id=session_id)
    await AgentUiAction.objects.filter(call_id=first["call_id"]).aupdate(outcome="ok")
    third = await publish_ui_action(action=JUDGE, arguments=args, session_id=session_id)

    assert third["status"] == "dispatched"
    assert third["call_id"] != first["call_id"]
    assert len(bus.published) == 2


@pytest.mark.asyncio
async def test_safe_action_is_never_reserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑨ ``ui_navigate``（safe）连发两次都要下发：重复执行无害，拦它只会弄坏律师的操作。

    把 ``reserve_dispatch`` 换成炸弹性替身：safe 动作**连占位都不该占**——它不写台账，
    也就不会撞上那条部分唯一索引。这条用例同时钉住了「幂等动作永不被去重」的实现方式：
    不是靠 ``action.idempotent`` 再判一次，而是因为它根本不进占位这条路径。
    """
    bus = _install_bus(monkeypatch, _FakeBus())

    async def _boom(**kwargs: Any) -> tuple[bool, str]:
        raise AssertionError("safe 动作不该占位（不写台账，也不该被拦）")

    monkeypatch.setattr("apps.agent.services.ui_action.audit.reserve_dispatch", _boom)
    session_id = _session_id()

    first = await publish_ui_action(action=NAVIGATE, arguments={"path": "/material-prep"}, session_id=session_id)
    second = await publish_ui_action(action=NAVIGATE, arguments={"path": "/material-prep"}, session_id=session_id)

    assert first["status"] == "dispatched"
    assert second["status"] == "dispatched"
    assert first["call_id"] != second["call_id"]
    assert len(bus.published) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_different_arguments_are_not_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑩ 参数不同（packId 815）→ 正常下发：去重是「同一份参数」，不是「同一个动作」。"""
    session = await _make_session("uidispatch-args")
    bus = _install_bus(monkeypatch, _FakeBus())
    session_id = str(session.session_id)

    first = await publish_ui_action(action=JUDGE, arguments={"packId": 814, "target": "done"}, session_id=session_id)
    second = await publish_ui_action(action=JUDGE, arguments={"packId": 815, "target": "done"}, session_id=session_id)

    assert first["status"] == "dispatched"
    assert second["status"] == "dispatched"
    assert second["call_id"] != first["call_id"]
    assert len(bus.published) == 2, "换了一个材料包就是另一次决定，不许被当成重复"


@pytest.mark.asyncio
async def test_no_channel_never_reaches_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑪ 没有会话 → 仍是 ``no_channel``，且**不进占位**（无会话无从竞争，也不该白写一行台账）。

    分支顺序也是断言：``no_channel`` 排在占位前面，没通道时连台账都不该碰。
    """
    bus = _install_bus(monkeypatch, _FakeBus())

    async def _boom(**kwargs: Any) -> tuple[bool, str]:
        raise AssertionError("没有会话时不该去占位")

    monkeypatch.setattr("apps.agent.services.ui_action.audit.reserve_dispatch", _boom)

    result = await publish_ui_action(action=JUDGE, arguments={"packId": 814, "target": "done"}, session_id=None)

    assert result["status"] == "no_channel"
    assert result["delivered"] is False
    assert bus.published == []
