"""UI 动作台账的**聚合统计**（``GET /agent/ui-actions/stats``）与列表的时间/决定过滤。

为什么这些断言值得写：台账已经能逐条查了，但「AI 这段时间帮我做了多少事、成了几个、
我拒过几个」是逐条翻不出来的问题。而汇总数字坏掉的形态全都是「看着合理」的：

- 统计没按用户过滤 → 报表里混进别人的按钮记录（动作历史不是会话共享资产）；
- 没结算的行被漏掉 / 被算成成功 → 总数与明细对不上，或者「没回执」在报表里变成「成功」；
- ``verified_rate`` 分母取了 ``total`` 或 0 → 0.78 变成 0.39，或「没有一行值得核实」
  被读成「全都核实失败」；
- ``not_checked``（没核实）与 ``verified=False``（核实了没变）混成一档 → 「我们没看」
  被报成「我们看了，库里没变」，这两件事的处理方式完全相反；
- 把 ``created_at - decided_at`` 叫成「延迟」而不说清不是执行耗时 → 报表上的 p95 会被
  当成「页面执行多慢」，而台账里根本没有执行完成时刻；
- 时间窗 / 动作名过滤只在 API 层做 → 分页一上就是错的数；
- ``days=0`` / ``days=999`` 直接报 500 → 前端传个 0 就白屏。

用例直接插台账行（``AgentUiAction.objects.acreate``）而不走写路径：报表要的是一些
写路径造不出来的组合（同一动作既核实过又没核实、30 天前的行）。写路径本身由
``test_ui_action_audit.py`` 钉住。

``django_db(transaction=True)`` + ``async`` 是必须的：这些用例走 async ORM，它在
asgiref 执行器连接上跑，普通事务包裹下看不见用例里创建的行（同 ``test_ui_action_audit.py``）。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.agent.models import AgentUiAction
from apps.agent.services.ui_action import audit, audit_query
from apps.organization.models import Lawyer

#: 清单里真实存在的两个动作名（报表按动作名分组，用真名才看得出「哪一类动作最忙」）。
JUDGE = "ui_material_prep_judge"
DELETE_PACK = "ui_material_prep_delete_pack"


async def _make_user(username: str) -> Lawyer:
    """异步建律师，不设口令：本文件不测登录，任何口令字面量都会被 detect-secrets 拦。"""
    user: Lawyer = await Lawyer.objects.acreate(username=username, real_name=f"统计律师-{username}")
    return user


async def _row(
    user: Lawyer,
    *,
    action: str = JUDGE,
    outcome: str = "ok",
    verified: bool | None = None,
    decision: str = "",
    days_ago: float = 0.0,
    dispatch_ms: int | None = None,
    risk: str = "confirm",
) -> str:
    """直接插一行台账，返回 ``call_id``。

    ``created_at`` 是 ``auto_now_add``（显式传值会被覆盖），所以「30 天前的那一行」只能
    插完再 ``aupdate``。``dispatch_ms`` = 审批决定到下发这一段（``decided_at`` 比
    ``created_at`` 早多少毫秒），用来钉 ``approval_to_dispatch_ms`` 的口径。
    """
    call_id = uuid.uuid4().hex
    created_at = timezone.now() - timedelta(days=days_ago)
    decided_at = None if dispatch_ms is None else created_at - timedelta(milliseconds=dispatch_ms)
    await AgentUiAction.objects.acreate(
        call_id=call_id,
        user=user,
        action=action,
        risk=risk,
        outcome=outcome,
        verified=verified,
        decision=decision,
        decided_at=decided_at,
    )
    if days_ago or dispatch_ms is not None:
        await AgentUiAction.objects.filter(call_id=call_id).aupdate(created_at=created_at)
    return call_id


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_stats_only_counts_own_rows() -> None:
    """① 两个用户各造行 → 报表只数自己的（与列表端点同口径）。"""
    mine = await _make_user("uistats-mine")
    stranger = await _make_user("uistats-stranger")
    await _row(mine, action=JUDGE, outcome="ok", verified=True)
    await _row(mine, action=DELETE_PACK, outcome="denied", decision="denied")
    await _row(stranger, action=JUDGE, outcome="ok", verified=True)
    await _row(stranger, action=JUDGE, outcome="error")

    report = await audit_query.stats_for_user(mine)

    assert report["total"] == 2, "别人的两行不许进我的报表"
    assert {item["action"] for item in report["by_action"]} == {JUDGE, DELETE_PACK}
    assert sum(report["by_outcome"].values()) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_outcome_counts_every_tier() -> None:
    """② ``by_outcome`` 五档都数：含 ``denied`` / ``expired``（从未执行过的那两类）。"""
    user = await _make_user("uistats-outcome")
    for outcome, decision in (
        ("ok", "approved"),
        ("error", ""),
        ("aborted", ""),
        ("denied", "denied"),
        ("expired", "expired"),
    ):
        await _row(user, outcome=outcome, decision=decision)

    report = await audit_query.stats_for_user(user)

    assert report["by_outcome"] == {"ok": 1, "error": 1, "denied": 1, "aborted": 1, "expired": 1}
    assert sum(report["by_outcome"].values()) == report["total"] == 5, "丢一类不报，总数就对不上"
    # ``decision`` 与 ``outcome`` 是两个主体的问题：这里只有 3 行有判定，另两行还没人判。
    assert report["approval"] == {"approved": 1, "denied": 1, "expired": 1}
    assert sum(report["approval"].values()) == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verified_rate_is_null_without_a_denominator() -> None:
    """③ ``verified_rate`` = 核实为真 / **核实非空**；分母为 0 → ``null``（不是 0）。"""
    user = await _make_user("uistats-rate")
    await _row(user, action=JUDGE, outcome="ok", verified=None)
    await _row(user, action=JUDGE, outcome="ok", verified=None)
    await _row(user, action=DELETE_PACK, outcome="ok", verified=None)
    await _row(user, action=DELETE_PACK, outcome="ok", verified=None)
    await _row(user, action=DELETE_PACK, outcome="ok", verified=True)

    report = await audit_query.stats_for_user(user)
    rates = {item["action"]: item["verified_rate"] for item in report["by_action"]}

    assert rates[JUDGE] is None, "一行都没核实过 → null，0 会被读成「全都核实失败」"
    assert rates[DELETE_PACK] == 1.0, "分母是「核实非空」= 1，不是 total = 3（那会算成 0.33）"
    assert [item["action"] for item in report["by_action"]] == [DELETE_PACK, JUDGE], "最忙的排前面"
    assert [item["total"] for item in report["by_action"]] == [3, 2]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_not_checked_is_not_a_verification_failure() -> None:
    """④ ``not_checked``（没核实）与 ``verified=False``（核实了没变）必须分开计。"""
    user = await _make_user("uistats-verified")
    await _row(user, outcome="ok", verified=True)
    await _row(user, outcome="ok", verified=False)
    await _row(user, outcome="ok", verified=None)
    await _row(user, outcome="error", verified=None)

    report = await audit_query.stats_for_user(user)

    # 四桶是一份划分：true / false 是两种结论，not_checked 是「页面报成功但没人核」，
    # unknown 是「没成功过、本来就没有可核实的对象」。
    assert report["verified"] == {"true": 1, "false": 1, "unknown": 1, "not_checked": 1}
    assert sum(report["verified"].values()) == report["total"] == 4


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_window_days_excludes_rows_older_than_window() -> None:
    """⑤ 时间窗：30 天前那一行不进 ``days=7``，进了 ``days=40``。"""
    user = await _make_user("uistats-window")
    await _row(user, outcome="ok", verified=True)
    await _row(user, outcome="ok", verified=True, days_ago=30)

    recent = await audit_query.stats_for_user(user, days=7)
    wide = await audit_query.stats_for_user(user, days=40)

    assert recent["window_days"] == 7
    assert recent["total"] == 1, "30 天前的行不该进 7 天窗口"
    assert wide["window_days"] == 40
    assert wide["total"] == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_action_filter() -> None:
    """⑥ ``action=`` 精确匹配；空串 = 不过滤。"""
    user = await _make_user("uistats-action")
    await _row(user, action=JUDGE, outcome="ok")
    await _row(user, action=JUDGE, outcome="denied", decision="denied")
    await _row(user, action=DELETE_PACK, outcome="ok")

    only_judge = await audit_query.stats_for_user(user, action=JUDGE)
    everything = await audit_query.stats_for_user(user)

    assert only_judge["total"] == 2
    assert [item["action"] for item in only_judge["by_action"]] == [JUDGE]
    assert only_judge["by_action"][0]["ok"] == 1 and only_judge["by_action"][0]["denied"] == 1
    assert everything["total"] == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_out_of_range_days_are_clamped() -> None:
    """⑦ ``days=0`` / ``days=999`` 夹到 1 / 90 继续算，不抛异常也不返回空报表。"""
    user = await _make_user("uistats-clamp")
    await _row(user, outcome="ok", verified=True, days_ago=2)

    zero = await audit_query.stats_for_user(user, days=0)
    huge = await audit_query.stats_for_user(user, days=999)

    assert zero["window_days"] == 1, "0 天夹到 1 天，而不是报 500 或恒空"
    assert zero["total"] == 0, "2 天前的行不进 1 天窗口——夹到 1 天，而不是「0 = 不过滤」"
    assert huge["window_days"] == 90, "999 天夹到上限 90"
    assert huge["total"] == 1
    assert audit_query.clamp_window_days("7") == 7, "HTTP 层给的是字符串，别抛"
    assert audit_query.clamp_window_days("x") == audit_query.STATS_WINDOW_DAYS_DEFAULT


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_endpoint_without_login_returns_empty_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑧ 未登录：全零结构 + ``error``，与同文件其余端点同一口径（不报 401、不查库）。"""
    from apps.agent.api import ui_api

    monkeypatch.setattr(ui_api, "_current_user", lambda _request: None)

    result = await ui_api.ui_action_stats(object())

    assert result["error"] == "未登录"
    assert result["total"] == 0
    assert result["window_days"] == audit_query.STATS_WINDOW_DAYS_DEFAULT
    assert result["by_action"] == []
    assert result["by_outcome"] == {"ok": 0, "error": 0, "denied": 0, "aborted": 0, "expired": 0}
    assert result["verified"] == {"true": 0, "false": 0, "unknown": 0, "not_checked": 0}
    # 夹边界也在这一层生效：未登录不该因为一个越界参数变成 500。
    assert (await ui_api.ui_action_stats(object(), days=999))["window_days"] == 90


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_approval_to_dispatch_is_named_for_what_it_measures() -> None:
    """⑨ 时间字段只报「审批→下发」，且**不**出现任何会被读成执行耗时的名字。"""
    user = await _make_user("uistats-latency")
    await _row(user, outcome="ok", verified=True, decision="approved", dispatch_ms=1000)
    await _row(user, outcome="ok", verified=True, decision="approved", dispatch_ms=3000)
    await _row(user, outcome="ok", verified=True)  # 没有 decided_at → 不进样本

    report = await audit_query.stats_for_user(user)

    assert report["approval_to_dispatch_ms"] == {"p50": 1000, "p95": 3000, "samples": 2}
    for misleading in ("latency_ms", "span_ms", "duration_ms"):
        assert misleading not in report, f"{misleading} 会被当成执行耗时，台账里没有执行完成时刻"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_truncation_keeps_true_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑩ 超过上限时只统计最近的行，``total`` 仍是真话、``truncated`` 说出来。"""
    user = await _make_user("uistats-truncated")
    for index in range(3):
        await _row(user, outcome="ok", verified=True, days_ago=index)
    monkeypatch.setattr(audit_query, "STATS_MAX_ROWS", 2)

    report = await audit_query.stats_for_user(user)

    assert report["truncated"] is True
    assert report["total"] == 3, "total 是窗口内的真实行数，不是样本量"
    assert sum(report["by_outcome"].values()) == 2, "明细只覆盖最近 2 行——所以两项可以不等"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_list_filters_by_decision_and_since_days() -> None:
    """⑪ 列表端点补的两个过滤：``decision`` 精确匹配、``since_days=0`` 保持不过滤。"""
    user = await _make_user("uistats-list")
    await _row(user, outcome="ok", decision="approved", days_ago=10)
    await _row(user, outcome="denied", decision="denied", days_ago=2)

    assert len(await audit_query.list_recent_for_user(user)) == 2, "不传就是不过滤（老行为）"
    denied = await audit_query.list_recent_for_user(user, decision="denied")
    assert [item["decision"] for item in denied] == ["denied"]
    assert len(await audit_query.list_recent_for_user(user, decision="approved")) == 1
    assert len(await audit_query.list_recent_for_user(user, since_days=7)) == 1
    assert len(await audit_query.list_recent_for_user(user, since_days=0)) == 2
    # 两个过滤叠起来也是库里做（AND），不是先筛一遍再筛一遍。
    assert len(await audit_query.list_recent_for_user(user, decision="denied", since_days=7)) == 1
    assert len(await audit_query.list_recent_for_user(user, decision="approved", since_days=7)) == 0
    # ``audit`` 上的旧入口仍然可用（re-export，签名向后兼容）。
    assert len(await audit.list_recent_for_user(user, outcome="ok")) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_list_endpoint_passes_new_filters_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑫ 端点必须把两个新参数真的传下去（漏传不报错，只会静默返回「不过滤」的结果）。"""
    from apps.agent.api import ui_api

    captured: dict[str, Any] = {}

    async def fake_list(_user: Any, **kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(ui_api.audit, "list_recent_for_user", fake_list)
    monkeypatch.setattr(ui_api, "_current_user", lambda _request: object())

    await ui_api.list_ui_actions(object(), decision="denied", since_days=7)

    assert captured["decision"] == "denied"
    assert captured["since_days"] == 7
