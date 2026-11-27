"""UI 动作审计 —— 把「AI 让页面干了什么 / 页面回了什么」落成可查的行（M1）。

## 写入口只有两个，且判定都收在本模块里

- :func:`record_dispatch`：下发成功后插一行（``outcome="unknown"``）；
- :func:`apply_receipt`：前端回执到达后就地更新那一行（幂等）。

**为什么把「该不该写」放进 :func:`record_dispatch` 而不是调用方**：判定散在调用侧，
早晚出现一条新路径忘了判——那张表就不是「高危动作台账」，而是「谁知道要写就写」的
抽样。收在这里之后，调用方只有一个动作：把 facts 交给它。

## 审计失败绝不打断下发

``publish_ui_action`` 的返回值是模型唯一的视野：为了写一行审计而抛异常，等于为了
台账牺牲掉「动作已经发生」这个事实。所以这里只 catch 具体异常
（``django.db.DatabaseError`` / ``ValueError``）并 ``logger.warning``：仓库的
``test_exception_ratchet`` 禁止扩大 ``except Exception``，而这两类正好覆盖
「库挂了 / JSON 不可序列化」全部真实失败形态。

## 为什么模块顶层只有常量与 docstring

``python -m apps.agent.services.ui_action --ts`` 要在**没有 Django settings** 的
进程里 import 整个包（生成器只碰 manifest / schema）。所以 Django 的模型与
``timezone`` 全部下沉到函数内（同 ``ack.py::_cache`` 的延迟 import）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: 需要落库的风险档。``safe`` 刻意不在内：量太大且无审计价值（见
#: ``models/ui_action.py`` 的模块 docstring）。
AUDITED_RISKS: frozenset[str] = frozenset({"confirm", "guarded"})

#: 审批关联窗口：批准后多久内下发的动作仍认作「这次批准放行的」。
#: 10 分钟足够覆盖「批完 → 模型下一轮调工具 → 页面执行」，再宽就会把上一次批准
#: 错认成这一次的（审批是一次性的，串批等于伪造授权）。
APPROVAL_WINDOW = timedelta(minutes=10)

#: ``outcome`` 的初始值。**不是** ``ok``：回执可能永远不到，默认成功就是撒谎。
OUTCOME_UNKNOWN = "unknown"

#: ``error_code`` / ``observed_location`` 的落库上限（与模型字段长度一致，
#: 超长在 PostgreSQL 上是 ``DataError``——整份回执会因此丢掉）。
CODE_MAX = 32
LOCATION_MAX = 300

#: 历史查询的每页硬上限（前端传再大也不给，避免一次拉全表）。
LIST_MAX_LIMIT = 200


async def record_dispatch(
    *,
    call_id: str,
    action_name: str,
    arguments: dict[str, Any],
    risk: str,
    session_id: str | None,
    delivered: bool,
) -> bool:
    """插入一行「动作已下发」；返回是否真的落库。

    ``session_id`` 为空时 ``session`` / ``user`` 留空：后台任务、未挂会话的直连调用
    都可能下发动作，这种行仍然有审计价值（谁在什么时候让 AI 干了什么）。

    **审批关联是 best-effort**：同会话、已批准、工具名以本动作名结尾、且决定时间在
    :data:`APPROVAL_WINDOW` 内的最近一条 ``AgentApproval``。找不到就留空而不是拒写——
    审批服务本身不做任何改动，这里只读。

    Returns:
        本行是否写入成功。``False`` 有两种来源：``safe`` 档刻意不写，或写库失败。
        调用方（``publish_ui_action``）**不检查**返回值：审计不该有权力否决下发。
    """
    if risk not in AUDITED_RISKS:
        return False

    # 延迟 import：本模块要能在无 Django settings 的进程里被 import（见模块 docstring）。
    from django.db import DatabaseError
    from django.utils import timezone

    from ...models import AgentApproval, AgentSession, AgentUiAction
    from ..session_service import _as_uuid

    try:
        session = None
        normalized = _as_uuid(session_id) if session_id else None
        if normalized is not None:
            session = await AgentSession.objects.filter(session_id=normalized).afirst()
        approved_by_id: int | None = None
        approved_at: datetime | None = None
        if session is not None:
            approval = (
                await AgentApproval.objects.filter(
                    session=session,
                    status=AgentApproval.Status.APPROVED,
                    tool_name__endswith=action_name,
                    decided_at__gte=timezone.now() - APPROVAL_WINDOW,
                )
                .order_by("-decided_at")
                .afirst()
            )
            if approval is not None:
                approved_by_id = approval.decided_by_id
                approved_at = approval.decided_at
        await AgentUiAction.objects.acreate(
            call_id=call_id,
            session=session,
            user_id=session.user_id if session is not None else None,
            action=action_name,
            arguments=arguments,
            risk=risk,
            approved_by_id=approved_by_id,
            approved_at=approved_at,
            delivered=delivered,
            outcome=OUTCOME_UNKNOWN,
        )
    except (DatabaseError, ValueError):
        logger.warning(
            "UI 动作审计落库失败（下发不受影响，只是少了这一行台账）: call_id=%s action=%s",
            call_id,
            action_name,
            exc_info=True,
        )
        return False
    return True


async def apply_receipt(call_id: str, *, outcome: str, code: str, location: str) -> bool:
    """把前端回执写到对应那一行上；返回本次是否**真的**更新了一行。

    **幂等靠一条条件 UPDATE**：``filter(call_id=..., outcome="unknown").aupdate(...)``。
    前端会重试（网络抖动 / 用户刷新），两次 POST 可能落在两个 worker 上；「先读后写」
    中间的窗口会让后到的重放覆盖第一份真实结果（第一次 ``ok``、重放 ``aborted``）——
    那等于让台账记下一次从未发生的执行。交给数据库做比较并写入，就不需要那把锁。

    ``error_code`` 只在 ``outcome="error"`` 时保留：别的结局带着 code，读表的人会把
    「中止」误读成路由故障。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError

    from ...models import AgentUiAction

    try:
        updated = await AgentUiAction.objects.filter(call_id=call_id, outcome=OUTCOME_UNKNOWN).aupdate(
            delivered=True,
            outcome=outcome,
            error_code=(code or "")[:CODE_MAX] if outcome == "error" else "",
            observed_location=(location or "")[:LOCATION_MAX],
        )
    except (DatabaseError, ValueError):
        logger.warning(
            "UI 动作回执落库失败（回执通道不受影响，只是台账仍显示 unknown）: call_id=%s",
            call_id,
            exc_info=True,
        )
        return False
    return bool(updated)


async def list_recent_for_user(user: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """当前用户自己的动作历史（新 → 旧）。

    **只按 ``user`` 过滤，不按会话共享**：同一会话被转交给同事后，新负责人也不该看见
    前任按过哪些高危按钮——动作历史是「谁让 AI 干了什么」，换成别人看就成了另一件事。

    Args:
        limit: 条数，clamp 到 1~:data:`LIST_MAX_LIMIT`（传 0 或负数按 1 处理）。

    Returns:
        每项 ``{session_id, action, risk, outcome, approved_by_name, created_at,
        observed_location}``。``created_at`` 是 ISO 8601 字符串（前端直接 ``new Date()``）；
        没有审批关联时 ``approved_by_name`` 为空串。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError

    from ...models import AgentUiAction

    bounded = max(1, min(int(limit), LIST_MAX_LIMIT))
    try:
        rows = [
            row
            async for row in AgentUiAction.objects.filter(user=user)
            .select_related("session", "approved_by")
            .order_by("-created_at")[:bounded]
        ]
    except (DatabaseError, ValueError):
        logger.warning("查询 UI 动作历史失败 user=%s", getattr(user, "pk", None), exc_info=True)
        return []
    return [
        {
            "session_id": str(row.session.session_id) if row.session is not None else "",
            "action": row.action,
            "risk": row.risk,
            "outcome": row.outcome,
            # ``Lawyer.__str__`` = real_name or username，台账里要人能认出的名字。
            "approved_by_name": str(row.approved_by) if row.approved_by is not None else "",
            "created_at": row.created_at.isoformat(),
            "observed_location": row.observed_location,
        }
        for row in rows
    ]
