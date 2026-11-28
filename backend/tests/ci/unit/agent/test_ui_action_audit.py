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
- 参数不脱敏 / 不记指纹 → 律师填的账号原样留在审计表里，或「批 A 执行 B」无从发现；
- 同键可以有两条在飞 / 结算与过期后依旧抢不到位 → 同一个写库被执行两遍，或律师想再做
  一次永远做不成（两个方向都是错，所以占位用例要成对钉住）。

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
from django.db import IntegrityError
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

    判定的位置也是断言的一部分：``publish_ui_action`` 只对 ``audit.AUDITED_RISKS`` 占位，
    而 ``audit.reserve_dispatch`` 自己也按 ``risk`` 再挡一道（两道都不是调用方随手写的
    if）——所以这里必须真的走一遍下发链路。
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
async def test_deleting_the_session_keeps_the_audit_row() -> None:
    """删会话不许连带删台账（2026-11-28 真机手测现场踩到的那条）。

    律师清理对话列表是常规操作，而台账是「谁让 AI 干过什么」的合规痕迹。``session`` 若是
    ``CASCADE``，清一下会话就能把它抹掉——实测删除测试会话时 4 行审计全部消失。所以这条
    用真实删除动作钉住：会话没了，行还在，只是 ``session`` 变 NULL。
    """
    user = await _make_user("uiaudit-cascade")
    session = await _make_session(user)
    await AgentUiAction.objects.acreate(
        call_id=uuid.uuid4().hex,
        session=session,
        user=user,
        action=JUDGE.name,
        arguments={"packId": 1, "target": "done"},
        risk=JUDGE.risk,
        outcome="ok",
    )

    await session.adelete()

    row = await AgentUiAction.objects.filter(user=user).afirst()
    assert row is not None, "删会话把审计行一起级联删掉了——合规痕迹被「清一下对话列表」抹掉"
    assert row.session_id is None, "会话引用应置空而不是留一个悬空 id"
    assert row.action == JUDGE.name and row.outcome == "ok", "除会话引用外，行的内容不许被动过"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_history_only_shows_own_rows() -> None:
    """两个用户各一条，``list_recent_for_user`` 只看见自己的（别人的按钮记录不共享）。"""
    mine = await _make_user("uiaudit-mine")
    stranger = await _make_user("uiaudit-stranger")
    my_session = await _make_session(mine)
    stranger_session = await _make_session(stranger)

    assert (
        await audit.reserve_dispatch(
            call_id=uuid.uuid4().hex,
            action_name=CONFIRM.name,
            arguments={"pack_id": 1},
            risk="confirm",
            session_id=str(my_session.session_id),
        )
    )[0]
    assert (
        await audit.reserve_dispatch(
            call_id=uuid.uuid4().hex,
            action_name=CONFIRM.name,
            arguments={"pack_id": 2},
            risk="guarded",
            session_id=str(stranger_session.session_id),
        )
    )[0]

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


async def _approval_denial(
    user: Lawyer,
    session: AgentSession,
    *,
    status: str,
    reason: str,
    decision: str = audit.DECISION_DENIED,
) -> AgentUiAction:
    """建一张指定状态的审批卡 → 走一次 ``record_denial`` → 把落下来的那一行查回来。

    三条「人拒绝 / 系统超时」用例只有 ``status`` 不同，合成一个帮手是为了让每条用例
    只剩下「我给它什么状态、台账该回什么」这一句断言。
    """
    approval = await AgentApproval.objects.acreate(
        session=session,
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 812, "target": "done"},
        risk_level="high",
        status=status,
        decided_by=user,
        decided_at=timezone.now(),
        decision_reason=reason,
    )
    created = await audit.record_denial(
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 812, "target": "done"},
        session_id=str(session.session_id),
        approval_id=approval.approval_id.hex,
        reason=reason,
        decision=decision,
    )
    assert created is True
    row = await AgentUiAction.objects.filter(call_id=f"approval:{approval.approval_id.hex}").afirst()
    assert row is not None, "被拒绝/超时的审批必须落一行（这是台账存在的理由）"
    return row


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_rejected_approval_records_denied() -> None:
    """① 审批行是 ``REJECTED`` → ``denied``（律师的决定）。

    调用方给的 ``decision`` 在这里刻意填成 ``expired``：能读到审批行时**以那一行为准**，
    而不是信调用方的猜测——两者要是能不一致，「他不同意」和「我们没人应答」就又能
    混成一档（这正是真机手测暴露的那条：超时被记成了人拒绝）。
    """
    user = await _make_user("uiaudit-denial-rejected")
    session = await _make_session(user)

    row = await _approval_denial(
        user,
        session,
        status=AgentApproval.Status.REJECTED,
        reason="材料还没齐，先别归案",
        decision=audit.DECISION_EXPIRED,
    )

    assert row.decision == "denied"
    assert row.outcome == "denied", "outcome 跟着 decision 走（都表示从未执行）"
    assert row.decision_note == "材料还没齐，先别归案", "律师的原话要留住"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_timeout_is_recorded_as_expired_not_denied() -> None:
    """② 审批行是 ``TIMEOUT``（闸门等满上限）→ ``expired``，不是 ``denied``。

    超时不是「他不同意」，是我们自己的 fail-closed。混成一档之后，「审批卡是不是形同
    虚设」就再也量不出来：每一张没人看到的卡都会在报表里显示成「律师拒绝过」。
    ``decision_note`` 必须自己说清这一点（它经常被单独导出给人看）。
    """
    user = await _make_user("uiaudit-denial-timeout")
    session = await _make_session(user)

    row = await _approval_denial(
        user,
        session,
        status=AgentApproval.Status.TIMEOUT,
        reason="用户拒绝或超时",
    )

    assert row.decision == "expired"
    assert row.outcome == "expired", "没执行过，但不是人拒绝的"
    assert "审批超时" in row.decision_note
    assert "用户拒绝或超时" in row.decision_note, "原来的 reason 也要留着"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_cancelled_is_recorded_as_expired() -> None:
    """③ 审批行是 ``CANCELLED``（客户端断开 / 进程收尾）→ 同样是 ``expired``。

    这条与超时同属「系统判的」：卡片随会话一起消失了，律师没有被给过拒绝的机会。
    """
    user = await _make_user("uiaudit-denial-cancelled")
    session = await _make_session(user)

    row = await _approval_denial(
        user,
        session,
        status=AgentApproval.Status.CANCELLED,
        reason="会话已结束",
    )

    assert row.decision == "expired"
    assert row.outcome == "expired"
    assert "审批超时" in row.decision_note


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_denial_without_approval_row_keeps_caller_decision() -> None:
    """④ 没有 ``approval_id``（策略拒绝这类不建卡的路径）→ 沿用调用方给的 ``decision``。

    判据是「能不能读到审批行」，不是「有没有传 approval_id」：读不到就没有事实可依，
    这时只能记调用方说的那个值（默认 ``denied``），台账不许自己编一个。
    """
    user = await _make_user("uiaudit-denial-no-card")
    session = await _make_session(user)
    common: dict[str, Any] = {
        "tool_name": f"{tool_prefix()}{JUDGE.name}",
        "tool_args": {"packId": 900, "target": "done"},
        "session_id": str(session.session_id),
        "reason": "策略拒绝",
    }

    assert await audit.record_denial(**common) is True
    default_row = await AgentUiAction.objects.filter(decision="denied").afirst()
    assert default_row is not None
    assert default_row.outcome == "denied", "默认值就是 denied"
    assert default_row.decision_note == "策略拒绝"

    assert await audit.record_denial(**common, decision=audit.DECISION_EXPIRED) is True
    expired_row = await AgentUiAction.objects.filter(decision="expired").afirst()
    assert expired_row is not None
    assert expired_row.outcome == "expired", "outcome 与 decision 不得脱钩"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_unknown_approval_id_still_writes_row() -> None:
    """⑤ 关联到一张不存在的审批卡 → 不抛，仍落行（沿用调用方给的值）。

    审批行可能已经被清理（换环境 / DB 重置 / 老数据），而「工具被拒过」这件事仍必须
    留痕：为了查一张没有的卡而整行不落，等于让审计随审批表的生命周期一起消失。
    """
    user = await _make_user("uiaudit-denial-ghost-card")
    session = await _make_session(user)
    ghost_id = uuid.uuid4().hex

    created = await audit.record_denial(
        tool_name=f"{tool_prefix()}{JUDGE.name}",
        tool_args={"packId": 901, "target": "done"},
        session_id=str(session.session_id),
        approval_id=ghost_id,
        reason="审批卡已不存在",
    )

    assert created is True
    row = await AgentUiAction.objects.filter(call_id=f"approval:{ghost_id}").afirst()
    assert row is not None
    assert row.approval_id is None, "关联不上就留空，不要指向一条不存在的行"
    assert row.decision == "denied", "读不到审批行 → 沿用调用方给的默认值"
    assert row.outcome == "denied"


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

    assert (
        await audit.reserve_dispatch(
            call_id=uuid.uuid4().hex,
            action_name=CONFIRM.name,
            arguments=raw,
            risk="confirm",
            session_id=str(session.session_id),
        )
    )[0]

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
    # 三行给不同的 ``pack_id``：同一会话里「同动作同参数」只能有一条在飞（占位的部分唯一
    # 索引），本用例要的是三条互不相干的台账行。
    for call_id, action_name, risk, pack_id in (
        (unknown_id, CONFIRM.name, "confirm", 1),
        (ok_id, CONFIRM.name, "guarded", 2),
        (error_id, "ui_other_write", "confirm", 1),
    ):
        assert (
            await audit.reserve_dispatch(
                call_id=call_id,
                action_name=action_name,
                arguments={"pack_id": pack_id},
                risk=risk,
                session_id=str(session.session_id),
            )
        )[0]
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


# ── 服务端幂等：占位的部分唯一索引 ────────────────────────────────
# 下面六条钉的是「同一动作同参数只允许一个在飞」的两个方向：冲突时必须挡住（①⑥），
# 而结算 / 过期 / 换键 / 无会话时必须放行（②③④⑤）——少一半就是「永远只能做一次」。


async def _reserve(
    session: AgentSession,
    call_id: str,
    *,
    arguments: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """一条占位的最小参数（本组用例只关心唯一键的那四列）。"""
    return await audit.reserve_dispatch(
        call_id=call_id,
        action_name=CONFIRM.name,
        arguments=arguments if arguments is not None else {"pack_id": 7},
        risk="confirm",
        session_id=str(session.session_id),
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_reserve_twice_on_same_key_only_first_wins() -> None:
    """① 同 (session, action, hash) 连占两次：第一次抢到，第二次被数据库挡下并交回在飞的 call_id。

    这一条钉的正是「先查后写」换成「先占位再下发」的理由：两个 worker 同时下发时**都会
    查空**（旧 ``find_unsettled`` 的洞），而 ``acreate`` 只能有一个成功。
    """
    session = await _make_session(await _make_user("uiaudit-reserve-twice"))
    first_id, second_id = uuid.uuid4().hex, uuid.uuid4().hex

    ok_first, ledger_first = await _reserve(session, first_id)
    ok_second, ledger_second = await _reserve(session, second_id)

    assert ok_first is True
    assert ledger_first == first_id, "抢到时交回自己的 call_id（占位行、下发帧、回执是同一个 id）"
    assert ok_second is False, "同键仍在飞：第二次占位必须插不进去"
    assert ledger_second == first_id, "抢不到时交回**在飞那条**的 call_id（模型据此取结果）"
    assert await AgentUiAction.objects.acount() == 1, "冲突不该多写一行"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_settled_row_releases_the_key() -> None:
    """② 第一行结算（``outcome="ok"``）后再占位 → 抢到：约束只约束「在飞」，不约束历史。"""
    session = await _make_session(await _make_user("uiaudit-reserve-settled"))
    first_id, second_id = uuid.uuid4().hex, uuid.uuid4().hex

    assert (await _reserve(session, first_id))[0] is True
    await AgentUiAction.objects.filter(call_id=first_id).aupdate(outcome="ok")

    ok_second, ledger_second = await _reserve(session, second_id)

    assert ok_second is True
    assert ledger_second == second_id
    assert await AgentUiAction.objects.acount() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_expired_row_is_swept_before_reserving() -> None:
    """③ 旧行过期后再占位 → 抢到，且旧行被扫成 ``expired``。

    ``expires_at`` 是唯一解除占位的条件，而「页面永不回执」时没有任何人会推动它——所以
    写之前必须扫一遍，否则一条永不结算的旧行会把这个键**永久占死**（律师想再做一次永远
    做不成）。
    """
    session = await _make_session(await _make_user("uiaudit-reserve-expired"))
    first_id, second_id = uuid.uuid4().hex, uuid.uuid4().hex

    assert (await _reserve(session, first_id))[0] is True
    await AgentUiAction.objects.filter(call_id=first_id).aupdate(expires_at=timezone.now() - timedelta(seconds=1))

    ok_second, ledger_second = await _reserve(session, second_id)

    assert ok_second is True
    assert ledger_second == second_id
    old = await AgentUiAction.objects.filter(call_id=first_id).afirst()
    assert old is not None
    assert old.outcome == "expired", "过期行必须落成终态，否则它还在索引里（键依旧被占死）"
    assert "占位" in old.decision_note, "为什么被判过期要留痕（否则事后只看到一行莫名的 expired）"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_different_session_or_arguments_do_not_conflict() -> None:
    """④ 不同会话 / 不同参数 → 都能抢到：去重键是「会话 + 动作 + 参数」，不是「动作」。"""
    user = await _make_user("uiaudit-reserve-keys")
    first_session = await _make_session(user)
    second_session = await _make_session(user)
    same_args = {"pack_id": 7}
    other_args = {"pack_id": 8}

    assert (await _reserve(first_session, uuid.uuid4().hex, arguments=same_args))[0] is True
    assert (await _reserve(first_session, uuid.uuid4().hex, arguments=other_args))[0] is True, (
        "换参数就是另一次决定，不该被自己的上一条堵住"
    )
    assert (await _reserve(second_session, uuid.uuid4().hex, arguments=same_args))[0] is True, (
        "别的会话里没有在飞的那一条（跨会话不该互相堵）"
    )
    assert await AgentUiAction.objects.acount() == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_null_session_never_conflicts() -> None:
    """⑤ 没有会话（``session_id=None``）→ 两次都抢到：NULL 不进那条部分唯一索引。

    PostgreSQL 的唯一索引里 NULL 互不相等（``NULLS DISTINCT``），所以约束对这些行**不生效**。
    可接受：没有会话的下发本来就没有可竞争的上下文（同一页面对应一个会话）。这条用例同时
    防止后来人「顺手」把 session 改成非空来「修好」它——代价是丢掉无会话下发的审计。
    """

    async def _reserve_without_session() -> tuple[bool, str]:
        return await audit.reserve_dispatch(
            call_id=uuid.uuid4().hex,
            action_name=CONFIRM.name,
            arguments={"pack_id": 7},
            risk="confirm",
            session_id=None,
        )

    assert (await _reserve_without_session())[0] is True
    assert (await _reserve_without_session())[0] is True
    assert await AgentUiAction.objects.filter(session__isnull=True).acount() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_partial_unique_index_rejects_second_unsettled_row() -> None:
    """⑥ 约束真的在数据库里：直接插两行同键 ``unknown`` → 第二条 ``IntegrityError``。

    绕开 ``reserve_dispatch`` 直插，是为了证明「同一动作同参数只允许一个在飞」不是应用层
    的巧合（某个分支忘了查），而是库自己拒绝：以后谁新开一条写入口，也逃不出这棵索引。
    """
    session = await _make_session(await _make_user("uiaudit-reserve-index"))
    shared: dict[str, Any] = {
        "session": session,
        "action": CONFIRM.name,
        "arguments": {"pack_id": 7},
        "arguments_hash": audit.arguments_hash_of({"pack_id": 7}),
        "risk": "confirm",
        "expires_at": timezone.now() + audit.RECEIPT_TTL,
    }

    await AgentUiAction.objects.acreate(call_id=uuid.uuid4().hex, **shared)
    with pytest.raises(IntegrityError):
        await AgentUiAction.objects.acreate(call_id=uuid.uuid4().hex, **shared)
