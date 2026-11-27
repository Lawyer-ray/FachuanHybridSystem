"""UI 动作的服务端效果核实（``verified`` 三态）。

为什么这些断言值得写：``outcome`` 的唯一来源是前端回执，也就是**页面自己说**它做完了。
而模型会把工具返回值当成事实转述给律师——法律场景里说错一次「已归案」就是事故。
所以「页面说成功之后，服务端再去看一眼库」这一步必须存在，且它的三种结论必须走到
三个不同的措词上：

- ``True``：「已由服务端核实」；
- ``False``：页面报成功但库里没变 → 返回值里必须出现**禁止断言**的措辞；
- ``None``（无法核实）：不许退化成 False（「我没看」≠「我看了没变」），也不许说成功。

还有两条结构性约束：动作没声明 ``verify`` 时**一个字段都不加**（返回值是冻结契约，
既有测试逐字比对），以及核实本身抛异常绝不能冒泡成「动作失败」——动作已经做完了，
核实只是附加证据。

``django_db(transaction=True)`` 是必须的：这些用例走 async ORM，它在 asgiref 执行器
连接上跑，普通事务包裹下看不见用例里创建的行（同 ``test_ui_action_audit.py``）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from django.utils import timezone

from apps.agent.models import AgentSession, AgentUiAction
from apps.agent.services.ui_action import ack, publish_ui_action, verify
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from apps.message_hub.models import InboxMessage, MessageSource
from apps.organization.models import Lawyer

#: 清单里唯一声明了 ``verify`` 的动作（``ui_material_prep_judge`` → ``material_prep_status``）。
JUDGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_judge")


def _action(name: str, verify_name: str | None) -> UiAction:
    """造一条测试动作：字段与清单同构，只换名字与核实器。

    ``publish_ui_action`` 不认识清单里的具体条目（它只读 ``action.verify`` 这类元数据），
    所以用例可以自带动作；真实核实器那几条仍然走清单里的 ``JUDGE``。
    """
    return UiAction(
        name=name,
        title="测试用写动作",
        describe="测试用：一次要人工审批、并且可以被服务端核实的写操作。",
        args_schema={
            "type": "object",
            "properties": {"packId": {"type": "integer"}, "target": {"type": "string"}},
            "required": ["packId", "target"],
            "additionalProperties": False,
        },
        risk="confirm",
        tier="direct",
        handler="material_prep_judge",
        verify=verify_name,
    )


class _FakeBus:
    """记录发布内容的最小假总线（与 ``test_ui_action_publish.py`` 同形）。"""

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


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认走 ``on`` 且关掉回执窗口，并清空进程内积压表（同 ``test_ui_action_audit.py``）。"""
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0")
    ack._PENDING.clear()


@pytest.fixture(autouse=True)
def _restore_verifiers() -> Iterator[None]:
    """每个用例结束后把核实器注册表恢复原状。

    注册表是进程级全局状态：用例注册的假核实器一旦留下来，后面用例的核实结论就会
    随机变成假的那一个——而「测试之间互相污染」是最难查的一类红。
    """
    snapshot = dict(verify.VERIFIERS)
    yield
    verify.VERIFIERS.clear()
    verify.VERIFIERS.update(snapshot)


def _install_bus(monkeypatch: pytest.MonkeyPatch) -> _FakeBus:
    bus = _FakeBus()
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


def _install_receipt(monkeypatch: pytest.MonkeyPatch, *, outcome: str = "ok", location: str = "/material-prep") -> None:
    """把回执直接塞进等待点。

    本文件钓的是「拿到 ``ok`` 回执**之后**做什么」，而等待/积压本身在
    ``test_ui_action_ack.py`` 里已经钉过了；真等 2 秒只会让三条用例各白等一轮。
    """

    async def _wait(call_id: str, timeout: float) -> dict[str, Any]:
        return {"outcome": outcome, "code": "", "detail": "", "location": location}

    monkeypatch.setattr(ack, "wait", _wait)


async def _make_session(username: str) -> AgentSession:
    """异步建律师 + 会话（async 用例里不能用同步 ORM）。"""
    user = await Lawyer.objects.acreate(username=username, real_name=f"核实用例-{username}")
    return await AgentSession.objects.acreate(title="动作核实用例", user=user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_action_without_verify_adds_no_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """① 动作没声明 ``verify`` → ``run_verifier`` 返回 None，publish 返回值里没有 verified 键。

    这条是既有契约的护栏：返回值是前端与模型两侧照抄的冻结形状，多一个恒为 null 的键
    就会让「有没有核实过」变得不可分辨。
    """
    session = await _make_session("uiverify-plain")
    _install_bus(monkeypatch)
    _install_receipt(monkeypatch)
    action = _action("ui_test_plain_write", verify_name=None)

    result = await publish_ui_action(
        action=action,
        arguments={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
    )

    assert result["observed"] is True
    assert result["outcome"] == "ok"
    assert "verified" not in result
    assert "verify_note" not in result
    assert await verify.run_verifier(action, {"packId": 812, "target": "done"}) is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verified_true_returns_server_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """② 核实通过 → 返回值带 ``verified=True``，note 换口径成「已由服务端核实」，并落库。

    「落库」这一半同样重要：模型看到的与事后查到的必须同源，否则审计里永远查不到
    这次核实到底怎么结论的。
    """
    session = await _make_session("uiverify-true")
    _install_bus(monkeypatch)
    _install_receipt(monkeypatch)

    @verify.verifier("fake_ok")
    async def _ok(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"verified": True, "note": "服务端核实通过：测试包 812 当前状态 done", "observed": {}}

    action = _action("ui_test_verified_ok", verify_name="fake_ok")
    result = await publish_ui_action(
        action=action,
        arguments={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
    )

    assert result["verified"] is True
    assert result["verify_note"] == "服务端核实通过：测试包 812 当前状态 done"
    assert "已由服务端核实" in result["note"]
    assert result["outcome"] == "ok", "核实不改变页面回执那一列"

    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.verified is True
    assert row.verify_note == "服务端核实通过：测试包 812 当前状态 done"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verified_false_forbids_completion_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """③ 页面报成功但核实不通过 → 返回值里必须出现**禁止断言已完成**的措辞。

    这是整套机制存在的唯一理由：模型只读这一句话，措辞松一格它就会对律师说「已完成」。
    所以这里断言关键词而不是整句（文案要能改，禁止断言的意图不能丢）。
    """
    session = await _make_session("uiverify-false")
    _install_bus(monkeypatch)
    _install_receipt(monkeypatch)

    @verify.verifier("fake_bad")
    async def _bad(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"verified": False, "note": "页面报成功但服务端核实不通过：库里仍是 todo", "observed": {}}

    action = _action("ui_test_verified_bad", verify_name="fake_bad")
    result = await publish_ui_action(
        action=action,
        arguments={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
    )

    assert result["verified"] is False
    note = result["note"]
    assert "服务端核实不通过" in note
    assert "不要" in note and "已完成" in note, "模型必须被明确禁止说「已完成」"
    assert "已由服务端核实" not in note

    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.verified is False
    # 回执那一列仍停在 unknown：改写 ``outcome`` 的是回执端点（本用例直接塞了回执、
    # 没走那条 POST），核实**不许**顺手把 ``outcome`` 也改掉——两列各说各的主体。
    assert row.outcome == "unknown"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_material_prep_status_reads_inbox_state() -> None:
    """④ 真实核实器：按 ``packId`` 读 ``InboxMessage.draft_state["status"]`` 与目标比对。

    三种结论都要有：一致 → True、不一致 → False、包不存在 → None（无法核实）。
    最后一档尤其要盯：把它写成 False 就等于对着一个不存在的包断言「律师的事没办成」。
    """
    source = await MessageSource.objects.acreate(display_name="核实用例来源", sync_since=timezone.now())
    done_pack = await InboxMessage.objects.acreate(
        source=source,
        message_id="verify-done",
        received_at=timezone.now(),
        draft_state={"status": "done"},
    )
    todo_pack = await InboxMessage.objects.acreate(
        source=source,
        message_id="verify-todo",
        received_at=timezone.now(),
        draft_state={"status": "todo"},
    )
    # draft_state 不是 dict（老消息 / 被别的链路写坏）：这是「无法核实」，不是「没成功」。
    odd_pack = await InboxMessage.objects.acreate(
        source=source,
        message_id="verify-odd",
        received_at=timezone.now(),
        draft_state=[],
    )

    hit = await verify.run_verifier(JUDGE, {"packId": done_pack.pk, "target": "done"})
    assert hit is not None
    assert hit["verified"] is True
    assert f"材料包 {done_pack.pk} 当前状态 done" in hit["note"]
    assert hit["observed"] == {"packId": done_pack.pk, "status": "done"}

    miss = await verify.run_verifier(JUDGE, {"packId": todo_pack.pk, "target": "done"})
    assert miss is not None
    assert miss["verified"] is False
    assert "库里仍是 todo" in miss["note"]
    assert "不得对律师说已完成" in miss["note"]

    gone = await verify.run_verifier(JUDGE, {"packId": 999_999_999, "target": "done"})
    assert gone is not None
    assert gone["verified"] is None, "包不存在 = 无法核实，不是「没成功」"
    assert "无法核实" in gone["note"]

    no_state = await verify.run_verifier(JUDGE, {"packId": odd_pack.pk, "target": "done"})
    assert no_state is not None
    assert no_state["verified"] is None, "没有草稿状态同样无法核实（不能猜成 todo）"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verifier_exception_does_not_bubble(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """⑤ 核实器抛异常 → 不冒泡、不把动作判成失败，只 warn 并落 ``verified=None``。

    动作已经做完了，核实失败只是一份缺失的附加证据；让它冒泡会变成「工具执行失败」，
    模型只能拿同样的参数重试——那是一次真正的重复写库。
    """
    session = await _make_session("uiverify-boom")
    _install_bus(monkeypatch)
    _install_receipt(monkeypatch)
    caplog.set_level(logging.WARNING, logger="apps.agent.services.ui_action.verify")

    @verify.verifier("fake_boom")
    async def _boom(arguments: dict[str, Any]) -> dict[str, Any]:
        raise KeyError("packId")

    action = _action("ui_test_verified_boom", verify_name="fake_boom")
    result = await publish_ui_action(
        action=action,
        arguments={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
    )

    assert result["status"] == "dispatched"
    assert result["observed"] is True
    assert result["verified"] is None
    assert "无法核实" in result["note"]
    assert "不要" in result["note"], "核不了也不许说成功"
    assert any("核实失败" in record.getMessage() for record in caplog.records)
