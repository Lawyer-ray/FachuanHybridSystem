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

from django.db import transaction

from apps.cases.services.case.case_visibility import accessible_case_ids, can_access_case
from apps.core.exceptions import ValidationException
from apps.doc_verify.models import VerificationDecision, VerificationRun
from apps.doc_verify.services.verify.query import DECIDED_ACTIONS, NEEDS_DECISION_STATES

#: 三种处置：接受（放行）/ 退回（客户改错了）/ 重出（我们自己改后重发）。
DECISION_ACTIONS: tuple[str, ...] = ("accept", "reject", "reissue")

#: 一次批量裁决最多处理多少条。上限不是为了保护数据库，是为了保护「这一批到底改了
#: 什么」：几百条挤在一个事务里，出错时没人能说清哪条已落库、哪条没有。再多的请分批。
MAX_BATCH_SIZE = 200

#: 逐条跳过的原因（机器可读）。批量里的一条脏 id 只跳过它自己，不整批失败。
SKIP_RUN_NOT_FOUND = "RUN_NOT_FOUND"
SKIP_CASE_FORBIDDEN = "CASE_FORBIDDEN"
SKIP_STATE_NOT_NEEDS_DECISION = "STATE_NOT_NEEDS_DECISION"
SKIP_ALREADY_DECIDED = "ALREADY_DECIDED"


def normalize_action(action: str) -> str:
    """裁决动作的**唯一**校验点：单条与批量都从这里过，两份口径迟早会漂。"""
    normalized = (action or "").strip()
    if normalized not in DECISION_ACTIONS:
        raise ValidationException(
            message=f"裁决动作不合法：{action!r}（只接受 {' / '.join(DECISION_ACTIONS)}）",
            errors={"action": list(DECISION_ACTIONS)},
        )
    return normalized


def record_decision(
    *,
    verification: Any,
    action: str,
    reason: str = "",
    decided_by: Any = None,
) -> Any:
    """记录一条裁决并返回新行；历史行一个字都不动。"""
    return VerificationDecision.objects.create(
        verification=verification,
        action=normalize_action(action),
        reason=(reason or "").strip(),
        decided_by=decided_by,
    )


def record_batch_decisions(
    *,
    run_ids: list[int],
    action: str,
    reason: str = "",
    decided_by: Any = None,
) -> dict[str, Any]:
    """批量记录裁决，返回 `{decided, skipped, items}`。

    三条硬约束：

    1. **逐条判**：不存在 / 不可见 / 不需要裁决 / 已有 accept|reject 的，只把**这一条**
       计入 `skipped` 并写明原因。批量最常见的用法是「把攒下的都过一遍」，其中夹杂
       一条脏 id 就整批 400，律师只会以为功能坏了；
    2. **每条各写一行**，绝不 update 历史（理由见模块 docstring）；
    3. 整个循环一个事务：落到一半失败时，调用方看到的是「一条都没落」，而不是
       半批已裁、半批未裁的中间态（重试时已裁的会被 `ALREADY_DECIDED` 跳过）。
    """
    normalized = normalize_action(action)
    ids = [int(run_id) for run_id in run_ids]
    if not ids:
        raise ValidationException(message="run_ids 不能为空", errors={"run_ids": "至少一条"})
    if len(ids) > MAX_BATCH_SIZE:
        raise ValidationException(
            message=f"一次最多裁决 {MAX_BATCH_SIZE} 条",
            errors={"run_ids": f"本次 {len(ids)} 条，最多 {MAX_BATCH_SIZE} 条"},
        )

    runs = {run.id: run for run in VerificationRun.objects.select_related("artifact").filter(id__in=ids)}
    decided_ids = set(
        VerificationDecision.objects.filter(verification_id__in=list(runs), action__in=DECIDED_ACTIONS).values_list(
            "verification_id", flat=True
        )
    )
    visible_case_ids = accessible_case_ids(decided_by)

    items: list[dict[str, Any]] = []
    decided = 0
    skipped = 0
    with transaction.atomic():
        for run_id in ids:
            run = runs.get(run_id)
            if run is None:
                items.append({"run_id": run_id, "skipped_reason": SKIP_RUN_NOT_FOUND})
                skipped += 1
                continue
            if not _case_visible(decided_by, run.artifact.case_id, visible_case_ids):
                items.append({"run_id": run_id, "skipped_reason": SKIP_CASE_FORBIDDEN})
                skipped += 1
                continue
            if run.state not in NEEDS_DECISION_STATES:
                items.append({"run_id": run_id, "skipped_reason": SKIP_STATE_NOT_NEEDS_DECISION})
                skipped += 1
                continue
            if run.id in decided_ids:
                items.append({"run_id": run_id, "skipped_reason": SKIP_ALREADY_DECIDED})
                skipped += 1
                continue
            decision = record_decision(
                verification=run,
                action=normalized,
                reason=reason,
                decided_by=decided_by,
            )
            # 同一 id 在一批里出现两次：第二次必须被当成「刚裁过」，否则同一条会落两行
            decided_ids.add(run.id)
            items.append({"run_id": run.id, "decision_id": decision.id})
            decided += 1
    return {"decided": decided, "skipped": skipped, "items": items}


def _case_visible(operator: Any, case_id: int | None, visible_case_ids: set[int] | None) -> bool:
    """与单条裁决的 `_assert_case_visible` 同一口径（没绑案件的基线不设限制）。

    `accessible_case_ids` 不含「无主案件」，而 `can_access_case` 认为无主案件对所有人
    开放——只用离线集合判，批量会在这里悄悄少处理几条。集合说不可见时再用权威判据
    复核一次；集合说可见就一定可见（指派/授权），不必再查。
    """
    if case_id is None or visible_case_ids is None or case_id in visible_case_ids:
        return True
    return can_access_case(operator, case_id)
