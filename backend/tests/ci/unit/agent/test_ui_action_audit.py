"""UI 动作审计台账（M1）的六条硬约束。

为什么这些断言值得写：台账是事后唯一能回答「这个动作到底成了没有」的东西，而它坏掉
的形态全都是「看着正常」的：

- ``safe`` 动作也写一行 → 表随对话线性膨胀，真出事时没人翻得动；
- 写了行却默认 ``ok`` → 所有「没回执」在报表里变成「成功」，法律场景里这是最不能出的错；
- 回执不落库 → 台账永远停在 ``unknown``，等于没记；
- 重复回执覆盖第一份 → 记下一次从未发生的执行；
- 查询不过滤用户 → 谁都能看见别人按过哪些高危按钮；
- 审批关联串批 → 把上一次批准当成这一次的授权。

回执通道本身的语义（等待 / 积压 / 幂等唤醒）在 ``test_ui_action_ack.py``，下发契约在
``test_ui_action_publish.py``，本文件只管台账。

``django_db(transaction=True)`` 是必须的：这些用例走 async ORM，它在 asgiref 执行器
连接上跑，普通事务包裹下看不见用例里创建的行（同 ``test_agent_usage.TestRecordRun``）。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.utils import timezone

from apps.agent.models import AgentApproval, AgentSession, AgentUiAction
from apps.agent.services.ui_action import ack, audit, publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from apps.organization.models import Lawyer

#: 清单里的 ``safe`` 档动作（本文件用它证明「safe 不落库」）。
NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")

#: 清单当前全是 ``safe``（见 manifest.py 末尾的 ``CONFIRM_ACTION_NAMES`` 注释），
#: 而台账存在的意义正是「高危动作留痕」，所以用例自带一条 ``confirm`` 动作：
#: 字段与清单同构，只换名字与风险档——``publish_ui_action`` 不认识清单里的具体条目。
CONFIRM: UiAction = UiAction(
    name="ui_delete_pack",
    title="删除材料包",
    describe="测试用：一次要人工审批的写操作。",
    args_schema={
        "type": "object",
        "properties": {"pack_id": {"type": "integer"}},
        "required": ["pack_id"],
        "additionalProperties": False,
    },
    risk="confirm",
    tier="direct",
    handler="deletePack",
)


class _FakeBus:
    """记录发布内容的最小假总线（与 ``test_ui_action_publish.py`` 同形）。

    只实现 ``publish_ui_action`` 真正调用的三个方法：多实现一个就等于在测试里养一份
    会跟着真实总线漂移的假货，而本文件钓的是台账，不是总线。
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


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认走 ``on`` 且关掉回执窗口，并清空进程内积压表。

    - ``FACHUAN_UI_ACTION``：本机 shell 里若导出过开关，用例会随环境变色；
    - ``FACHUAN_UI_ACTION_ACK_WAIT=0``：本文件钓的是台账，等回执的语义在
      ``test_ui_action_ack.py``；不关窗口每条用例都要白等 2s；
    - 积压表：没等到回执的动作会被登记进去，跨用例残留会让 ``earlier_results``
      随机出现在后面用例的返回值里。
    """
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0")
    ack._PENDING.clear()


def _install_bus(monkeypatch: pytest.MonkeyPatch, bus: _FakeBus) -> _FakeBus:
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


async def _make_user(username: str) -> Lawyer:
    """异步建律师，不设口令：本文件不测登录，任何口令字面量都会被 detect-secrets 拦。

    async 用例里不能用同步 ORM（``SynchronousOnlyOperation``），所以连造数据也走 ``a*``。
    """
    return await Lawyer.objects.acreate(username=username, real_name=f"审计律师-{username}")


async def _make_session(user: Lawyer) -> AgentSession:
    return await AgentSession.objects.acreate(title="动作审计用例", user=user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_safe_action_writes_no_audit_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """``safe`` 档不落库：它没有业务副作用，量还大（台账只留高危）。

    判定的位置也是断言的一部分：调用方（``publish_ui_action``）不判，由
    ``audit.record_dispatch`` 自己挡——所以这里必须真的走一遍下发链路。
    """
    user = await _make_user("uiaudit-safe")
    session = await _make_session(user)
    _install_bus(monkeypatch, _FakeBus())

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/"}, session_id=str(session.session_id))

    assert result["status"] == "dispatched"
    assert (await AgentUiAction.objects.acount()) == 0, "safe 动作不该在台账里留行"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_confirm_action_records_one_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """``confirm`` 档下发成功 → 恰好一行，``outcome`` 必须是 ``unknown`` 而不是 ``ok``。"""
    user = await _make_user("uiaudit-confirm")
    session = await _make_session(user)
    _install_bus(monkeypatch, _FakeBus())

    result = await publish_ui_action(
        action=CONFIRM,
        arguments={"pack_id": 7},
        session_id=str(session.session_id),
    )

    assert result["status"] == "dispatched"
    assert result["delivered"] is True
    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.outcome == "unknown", "回执还没来，台账不能默认成功"
    assert row.delivered is True
    assert row.risk == "confirm"
    assert row.action == CONFIRM.name
    assert row.arguments == {"pack_id": 7}
    assert row.session_id == session.pk
    assert row.user_id == user.pk
    assert row.approved_by_id is None, "没有审批行时留空，而不是拒绝写这一行"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_receipt_updates_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """回执到达 → ``outcome`` / ``error_code`` / ``observed_location`` 就地更新。"""
    session = await _make_session(await _make_user("uiaudit-receipt"))
    _install_bus(monkeypatch, _FakeBus())
    result = await publish_ui_action(action=CONFIRM, arguments={"pack_id": 7}, session_id=str(session.session_id))

    updated = await audit.apply_receipt(
        result["call_id"],
        outcome="error",
        code="route_unreachable",
        location="/material-prep?stage=done",
    )

    assert updated is True
    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.outcome == "error"
    assert row.error_code == "route_unreachable"
    assert row.observed_location == "/material-prep?stage=done"
    assert row.delivered is True, "收到回执说明页面确实在执行这一条上"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_second_receipt_does_not_overwrite_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """重复回执（前端重试）不覆盖第一份：第二次返回 ``False``，行还是第一次的结局。"""
    session = await _make_session(await _make_user("uiaudit-replay"))
    _install_bus(monkeypatch, _FakeBus())
    result = await publish_ui_action(action=CONFIRM, arguments={"pack_id": 7}, session_id=str(session.session_id))

    first = await audit.apply_receipt(result["call_id"], outcome="ok", code="", location="/material-prep")
    second = await audit.apply_receipt(result["call_id"], outcome="aborted", code="manual", location="/elsewhere")

    assert first is True
    assert second is False, "第二份回执不该再写进去"
    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.outcome == "ok"
    assert row.error_code == ""
    assert row.observed_location == "/material-prep"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_history_only_shows_own_rows() -> None:
    """两个用户各一条，``list_recent_for_user`` 只看见自己的（别人的按钮记录不共享）。"""
    mine = await _make_user("uiaudit-mine")
    stranger = await _make_user("uiaudit-stranger")
    my_session = await _make_session(mine)
    stranger_session = await _make_session(stranger)

    assert await audit.record_dispatch(
        call_id=uuid.uuid4().hex,
        action_name=CONFIRM.name,
        arguments={"pack_id": 1},
        risk="confirm",
        session_id=str(my_session.session_id),
        delivered=True,
    )
    assert await audit.record_dispatch(
        call_id=uuid.uuid4().hex,
        action_name=CONFIRM.name,
        arguments={"pack_id": 2},
        risk="guarded",
        session_id=str(stranger_session.session_id),
        delivered=False,
    )

    items = await audit.list_recent_for_user(mine)

    assert len(items) == 1, "只该看见自己那一条"
    item = items[0]
    assert item["session_id"] == str(my_session.session_id)
    assert item["action"] == CONFIRM.name
    assert item["risk"] == "confirm"
    assert item["outcome"] == "unknown"
    assert item["approved_by_name"] == ""
    assert item["observed_location"] == ""
    assert isinstance(item["created_at"], str) and "T" in item["created_at"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_approval_within_window_is_linked(monkeypatch: pytest.MonkeyPatch) -> None:
    """窗口内的已批准审批行 → 台账记下批准人与批准时间（审批服务本身不改）。"""
    user = await _make_user("uiaudit-approver")
    session = await _make_session(user)
    _install_bus(monkeypatch, _FakeBus())
    await AgentApproval.objects.acreate(
        session=session,
        tool_name=f"mcp__fachuan__{CONFIRM.name}",
        tool_args={"pack_id": 7},
        risk_level="high",
        status=AgentApproval.Status.APPROVED,
        decided_by=user,
        decided_at=timezone.now(),
    )

    result = await publish_ui_action(action=CONFIRM, arguments={"pack_id": 7}, session_id=str(session.session_id))

    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.approved_by_id == user.pk
    assert row.approved_at is not None
