"""UI 动作审计台账（M1 + 信任层）的硬约束。

为什么这些断言值得写：台账是事后唯一能回答「这个动作到底成了没有、他到底同不同意」的
东西，而它坏掉的形态全都是「看着正常」的：

- ``safe`` 动作也写一行 → 表随对话线性膨胀，真出事时没人翻得动；
- 写了行却默认 ``ok`` → 所有「没回执」在报表里变成「成功」，法律场景里这是最不能出的错；
- **被拒绝的审批不落行** → 「他明确拒绝过什么」事后无法回答（拒绝是决定，不是没事发生）；
- 回执不落库 → 台账永远停在 ``unknown``，等于没记；
- 重复/迟到回执覆盖第一份 → 记下一次从未发生（或早已作废）的执行；
- 查询不过滤用户 → 谁都能看见别人按过哪些高危按钮；
- 审批关联串批 → 把上一次批准当成这一次的授权；
- 参数不脱敏 / 不记指纹 → 律师填的账号原样留在审计表里，或「批 A 执行 B」无从发现。

回执通道本身的语义（等待 / 积压 / 幂等唤醒）在 ``test_ui_action_ack.py``，下发契约在
``test_ui_action_publish.py``，服务端效果核实（``verified``）在
``test_ui_action_verify.py``；本文件只管台账。

``django_db(transaction=True)`` 是必须的：这些用例走 async ORM，它在 asgiref 执行器
连接上跑，普通事务包裹下看不见用例里创建的行（同 ``test_agent_usage.TestRecordRun``）。
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.agent.backends.toolface import tool_prefix
from apps.agent.models import AgentApproval, AgentSession, AgentUiAction
from apps.agent.services.ui_action import ack, audit, publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from apps.organization.models import Lawyer

#: 清单里的 ``safe`` 档动作（本文件用它证明「safe 不落库」）。
NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")

#: 清单里唯一的 ``confirm`` 动作。拒绝留痕按**清单**查名字（见 ``audit.record_denial``），
#: 所以拒绝用例必须用它，而不是下面那条测试专用的假动作——假动作查不到正好是 ③ 的断言。
JUDGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_judge")

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
    user: Lawyer = await Lawyer.objects.acreate(username=username, real_name=f"审计律师-{username}")
    return user


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
    """窗口内的已批准审批行 → 台账记下批准人、时间与**审批单本身**（审批服务不改）。"""
    user = await _make_user("uiaudit-approver")
    session = await _make_session(user)
    _install_bus(monkeypatch, _FakeBus())
    decided_at = timezone.now()
    approval = await AgentApproval.objects.acreate(
        session=session,
        tool_name=f"{tool_prefix()}{CONFIRM.name}",
        tool_args={"pack_id": 7},
        risk_level="high",
        status=AgentApproval.Status.APPROVED,
        decided_by=user,
        decided_at=decided_at,
    )

    result = await publish_ui_action(action=CONFIRM, arguments={"pack_id": 7}, session_id=str(session.session_id))

    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.approved_by_id == user.pk
    assert row.approved_at is not None
    # 新三列是「谁批的」的正式答案：审批单外键 + 决定 + 决定时间。
    assert row.approval_id == approval.pk, "按 approval_id 精确关联，而不是只靠时间窗口猜"
    assert row.decision == "approved"
    assert row.decided_at is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_denied_approval_writes_row() -> None:
    """① 律师拒绝 → 台账要有一行（``outcome`` 与 ``decision`` 都是 ``denied``）。

    这是本轮补的第一个真缺陷：拒绝以前完全不留痕，「他明确拒绝过什么」事后无法回答。
    ``approved_at`` 必须为空——那一列记的是「谁放的」，拒绝时没有人放。
    """
    user = await _make_user("uiaudit-denied")
    session = await _make_session(user)
    approval = await AgentApproval.objects.acreate(
        session=session,
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 812, "target": "done"},
        risk_level="high",
        status=AgentApproval.Status.REJECTED,
        decided_by=user,
        decided_at=timezone.now(),
        decision_reason="材料还没齐，先别归案",
    )

    created = await audit.record_denial(
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
        approval_id=approval.approval_id.hex,
        reason="材料还没齐，先别归案",
    )

    assert created is True
    row = await AgentUiAction.objects.filter(call_id=f"approval:{approval.approval_id.hex}").afirst()
    assert row is not None
    assert row.outcome == "denied", "拒绝是终态，不能停在 unknown（那会被人当成「还不确定」）"
    assert row.decision == "denied"
    assert row.decision_note == "材料还没齐，先别归案", "律师的原话要留住"
    assert row.approval_id == approval.pk
    assert row.action == JUDGE.name, "存短名：与清单、前端执行器同一套词"
    assert row.risk == "confirm"
    assert row.delivered is False, "没执行过就没有送达"
    assert row.approved_at is None and row.approved_by_id is None
    assert row.session_id == session.pk
    assert row.user_id == user.pk
    assert row.arguments == {"packId": 812, "target": "done"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_repeated_denial_keeps_one_row() -> None:
    """② 同一张卡的重复拒绝只有一行（前端重发 / 后端重试都不该多记一次）。"""
    session = await _make_session(await _make_user("uiaudit-denial-twice"))
    approval = await AgentApproval.objects.acreate(
        session=session,
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 812, "target": "filed"},
        risk_level="high",
        status=AgentApproval.Status.REJECTED,
        decided_at=timezone.now(),
    )

    kwargs: dict[str, Any] = {
        "tool_name": f"{tool_prefix()}{JUDGE.name}",
        "tool_args": {"packId": 812, "target": "filed"},
        "session_id": str(session.session_id),
        "approval_id": approval.approval_id.hex,
        "reason": "不接这个",
    }
    first = await audit.record_denial(**kwargs)
    second = await audit.record_denial(**kwargs)

    assert first is True
    assert second is False, "第二次不再落行（幂等靠 get_or_create 的 call_id）"
    assert await AgentUiAction.objects.filter(call_id=f"approval:{approval.approval_id.hex}").acount() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_denial_ignores_unlisted_or_safe_tools() -> None:
    """③ 清单外工具 / ``safe`` 档 → 不落行。

    ``record_denial`` 会被**所有**工具的拒绝路径调用（审批闸门的 ``if not approved:``
    分支），所以「该不该记」必须由它自己挡：把每个被策略拒掉的普通工具都记进来，
    真事就沉底了。
    """
    assert (
        await audit.record_denial(
            tool_name=f"{tool_prefix()}delete_case",
            tool_args={"case_id": 1},
            session_id=None,
            approval_id=uuid.uuid4().hex,
            reason="策略拒绝",
        )
        is False
    ), "不在清单里 → 静默跳过"
    assert (
        await audit.record_denial(
            tool_name=f"{tool_prefix()}{NAVIGATE.name}",
            tool_args={"path": "/"},
            session_id=None,
            approval_id=uuid.uuid4().hex,
            reason="策略拒绝",
        )
        is False
    ), "safe 档没有审计价值 → 静默跳过"
    assert await AgentUiAction.objects.acount() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_receipt_within_window_updates_then_row_is_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """④ 窗口内的回执改结局，之后**任何**回执都改不动（终态不可变）。

    另外钉两件下发时该落的事：``expires_at`` = now + :data:`audit.RECEIPT_TTL`、``batch_id``
    与批次一致（审核「这一批 5 步」时要有东西能把它们串起来）。
    """
    session = await _make_session(await _make_user("uiaudit-terminal"))
    _install_bus(monkeypatch, _FakeBus())

    result = await publish_ui_action(
        action=CONFIRM,
        arguments={"pack_id": 7},
        session_id=str(session.session_id),
        batch_id="batch-test-1",
    )

    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.expires_at is not None
    remaining = row.expires_at - timezone.now()
    assert timedelta(seconds=280) < remaining <= audit.RECEIPT_TTL, "回执窗口必须是 RECEIPT_TTL"
    assert row.batch_id == "batch-test-1"

    first = await audit.apply_receipt(result["call_id"], outcome="ok", code="", location="/material-prep")
    second = await audit.apply_receipt(result["call_id"], outcome="error", code="boom", location="/elsewhere")

    assert first is True
    assert second is False, "已在终态的行永不改写（MCP tasks 的「cancelled 必须保持 cancelled」）"
    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.outcome == "ok"
    assert row.error_code == "", "第二份回执的 code 也不许渗进来"
    assert row.observed_location == "/material-prep"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_late_receipt_marks_row_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑤ 超过 ``expires_at`` 的回执 → 那一行落成 ``expired``，且**不**被改写成 ok。

    「页面后来说它成功了，但那时已经晚于窗口」本身是有价值的事实，所以原始结局要进
    ``decision_note``；但结论只能是 ``expired``——我们早已在别处按「没成功」处理过。
    """
    session = await _make_session(await _make_user("uiaudit-late"))
    _install_bus(monkeypatch, _FakeBus())
    result = await publish_ui_action(action=CONFIRM, arguments={"pack_id": 7}, session_id=str(session.session_id))
    await AgentUiAction.objects.filter(call_id=result["call_id"]).aupdate(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    marked = await audit.apply_receipt(result["call_id"], outcome="ok", code="", location="/material-prep")

    assert marked is True, "它确实改写了那一行——只不过写进去的是 expired，不是回执说的 ok"
    row = await AgentUiAction.objects.filter(call_id=result["call_id"]).afirst()
    assert row is not None
    assert row.outcome == "expired"
    assert "晚于回执窗口" in row.decision_note
    assert "ok" in row.decision_note, "原始结局要留在 note 里（否则事后不知道页面到底说了什么）"
    assert row.observed_location == "", "过期的回执不写地址：那会让人以为它真的执行了"

    # 再迟到一次也不会翻案（expired 同样是终态）。
    assert await audit.apply_receipt(result["call_id"], outcome="error", code="x", location="/z") is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_arguments_are_sanitized_before_storage() -> None:
    """⑥ ``arguments`` 进库前脱敏（快照那条路一直走 ``scrub_for_storage``，台账也必须走）。

    不脱敏的后果是具体而丑的：律师填在表单里的账号/凭证原样留在审计表里，而那张表的
    读者恰恰是事后翻旧账的人（权限比前台宽）。
    """
    session = await _make_session(await _make_user("uiaudit-scrub"))
    raw: dict[str, Any] = {"pack_id": 7, "account": "北京某某公司账户"}

    assert await audit.record_dispatch(
        call_id=uuid.uuid4().hex,
        action_name=CONFIRM.name,
        arguments=raw,
        risk="confirm",
        session_id=str(session.session_id),
        delivered=True,
    )

    row = await AgentUiAction.objects.order_by("-created_at").afirst()
    assert row is not None
    assert row.arguments["account"] != raw["account"]
    assert "***" in row.arguments["account"]
    assert raw["account"] not in json.dumps(row.arguments, ensure_ascii=False)
    assert row.arguments["pack_id"] == 7, "非敏感字段原样保留（脱敏不是把参数整个抹掉）"
    # 指纹按**原始**参数算：脱敏后的值会把两个不同的账号算成同一个哈希。
    assert row.arguments_hash == audit.arguments_hash_of(raw)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_arguments_hash_ignores_key_order_and_tracks_values() -> None:
    """⑦ 参数指纹：键序不影响、值一定会影响（这条指纹存在的唯一理由是防「批 A 执行 B」）。"""
    ordered = audit.arguments_hash_of({"packId": 812, "target": "done"})
    reordered = audit.arguments_hash_of({"target": "done", "packId": 812})
    changed = audit.arguments_hash_of({"packId": 812, "target": "filed"})

    assert ordered == reordered, "键序是书写习惯，不该改变指纹"
    assert ordered != changed, "值变了指纹必须变，否则拦不住换参数执行"
    assert len(ordered) == 64
    assert set(ordered) <= set("0123456789abcdef")
    assert audit.arguments_hash_of({"name": "张三"}) != audit.arguments_hash_of({"name": "李四"})


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_history_filters() -> None:
    """⑧ list 的三个过滤：``action`` / ``outcome`` / ``risk``，空串 = 不过滤。"""
    user = await _make_user("uiaudit-filter")
    session = await _make_session(user)
    unknown_id = uuid.uuid4().hex
    ok_id = uuid.uuid4().hex
    error_id = uuid.uuid4().hex
    for call_id, action_name, risk in (
        (unknown_id, CONFIRM.name, "confirm"),
        (ok_id, CONFIRM.name, "guarded"),
        (error_id, "ui_other_write", "confirm"),
    ):
        assert await audit.record_dispatch(
            call_id=call_id,
            action_name=action_name,
            arguments={"pack_id": 1},
            risk=risk,
            session_id=str(session.session_id),
            delivered=True,
        )
    assert await audit.apply_receipt(ok_id, outcome="ok", code="", location="/a")
    assert await audit.apply_receipt(error_id, outcome="error", code="route_unreachable", location="/b")

    assert len(await audit.list_recent_for_user(user)) == 3
    assert {item["action"] for item in await audit.list_recent_for_user(user, action=CONFIRM.name)} == {CONFIRM.name}
    assert [item["outcome"] for item in await audit.list_recent_for_user(user, outcome="ok")] == ["ok"]
    assert len(await audit.list_recent_for_user(user, risk="confirm")) == 2
    assert len(await audit.list_recent_for_user(user, risk="guarded", outcome="ok")) == 1
    assert await audit.list_recent_for_user(user, outcome="denied") == []

    item = (await audit.list_recent_for_user(user, outcome="ok"))[0]
    # 新字段一个都不许少：前端历史列表与事后审计都靠它们。
    assert item["decision"] == "", "用例里没有审批行，决定列就留空（不拿时间窗口去猜）"
    assert isinstance(item["decided_at"], str)
    assert item["verified"] is None, "没核实过就是 None（不是 False）"
    assert item["verify_note"] == ""
    assert item["batch_id"] == ""
