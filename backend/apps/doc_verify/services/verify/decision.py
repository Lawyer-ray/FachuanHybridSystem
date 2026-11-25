"""律师裁决：accept / reject / reissue，**append-only**。

## 为什么这里只能 create

在生产里「改一下上次那条裁决」，等于把「谁在什么时候看过什么」这个事实
改写掉。裁决写错了就再记一条，历史两条都在——出事时能证明律师看过，
才是这张表存在的理由。所以本模块没有 update/delete 的入口，也不该有。

## 为什么只认三个值

每多一个值，前端要决定怎么显示、待裁决清单要决定怎么过滤。没有产品语义的
值会让「已裁决」变成一句空话（记了一笔谁也不知道算不算处置的动作）。
"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException
from apps.doc_verify.models import VerificationDecision

#: 三种处置：接受（放行）/ 退回（客户改错了）/ 重出（我们自己改后重发）。
DECISION_ACTIONS: tuple[str, ...] = ("accept", "reject", "reissue")


def record_decision(
    *,
    verification: Any,
    action: str,
    reason: str = "",
    decided_by: Any = None,
) -> Any:
    """记录一条裁决并返回新行；历史行一个字都不动。"""
    normalized = (action or "").strip()
    if normalized not in DECISION_ACTIONS:
        raise ValidationException(
            message=f"裁决动作不合法：{action!r}（只接受 {' / '.join(DECISION_ACTIONS)}）",
            errors={"action": list(DECISION_ACTIONS)},
        )
    return VerificationDecision.objects.create(
        verification=verification,
        action=normalized,
        reason=(reason or "").strip(),
        decided_by=decided_by,
    )
