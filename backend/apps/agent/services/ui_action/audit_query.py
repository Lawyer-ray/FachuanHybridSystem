"""UI 动作台账的**只读**查询 —— 动作历史列表（M1）。

写路径（占位 / 送达 / 回执 / 核实 / 拒绝留痕）全在 :mod:`.audit`；本模块只读，不写一行。
「为什么只按 ``user`` 过滤、不按会话共享」的论证在 :func:`list_recent_for_user` 的 docstring 里。

**依赖方向只有 audit → audit_query**：查询不 import 写路径，否则两个模块成环。

**为什么模块顶层没有 Django 符号**：与 :mod:`.audit` 同一条纪律（完整论证见它的模块
docstring）——``python -m apps.agent.services.ui_action --ts`` 要在没有 Django settings 的
进程里 import 整个包，所以 Django 的模型一律下沉到函数内。

``outcome="unknown"`` 是「未结算」的唯一取值；本模块只把它当调用方传进来的过滤值，不另建
常量（写侧同一个字面量见 :data:`audit.OUTCOME_UNKNOWN`，两侧不得各写一套常量）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 历史查询的每页硬上限（前端传再大也不给，避免一次拉全表）。
LIST_MAX_LIMIT = 200


async def list_recent_for_user(
    user: Any,
    *,
    limit: int = 50,
    action: str = "",
    outcome: str = "",
    risk: str = "",
) -> list[dict[str, Any]]:
    """当前用户自己的动作历史（新 → 旧）。

    **只按 ``user`` 过滤，不按会话共享**：同一会话被转交给同事后，新负责人也不该看见
    前任按过哪些高危按钮——动作历史是「谁让 AI 干了什么」，换成别人看就成了另一件事。

    Args:
        limit: 条数，clamp 到 1~:data:`LIST_MAX_LIMIT`（传 0 或负数按 1 处理）。
        action / outcome / risk: 精确匹配的过滤条件，**空串 = 不过滤**。三个都做成
            「空串即全部」而不是 ``None``：查询参数在 HTTP 层天然是字符串，让 None 与
            "" 表示同一件事只会在两端各写一个分支。

    Returns:
        每项 ``{session_id, action, risk, outcome, decision, decided_at, verified,
        verify_note, batch_id, approved_by_name, created_at, observed_location}``。
        时间字段是 ISO 8601 字符串（前端直接 ``new Date()``），为空时给空串；
        没有审批关联时 ``approved_by_name`` 为空串，``verified`` 保持 ``None``
        （「无法核实」与「没核实过」在列表里同形，细节看 ``verify_note``）。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError

    from ...models import AgentUiAction

    bounded = max(1, min(int(limit), LIST_MAX_LIMIT))
    filters: dict[str, str] = {}
    if action:
        filters["action"] = action
    if outcome:
        filters["outcome"] = outcome
    if risk:
        filters["risk"] = risk
    try:
        rows = [
            row
            async for row in AgentUiAction.objects.filter(user=user, **filters)
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
            "decision": row.decision,
            "decided_at": row.decided_at.isoformat() if row.decided_at is not None else "",
            "verified": row.verified,
            "verify_note": row.verify_note,
            "batch_id": row.batch_id,
            # ``Lawyer.__str__`` = real_name or username，台账里要人能认出的名字。
            "approved_by_name": str(row.approved_by) if row.approved_by is not None else "",
            "created_at": row.created_at.isoformat(),
            "observed_location": row.observed_location,
        }
        for row in rows
    ]
