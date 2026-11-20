"""`Decision` 落库与回读（append-only 裁决台账）。

## 只做两件事

1. ``record_decision``：冻结契约 ``Decision`` → ``ContractDecision`` 一行；
2. ``load_decision``：按 id 回读，**逐字段还原**成契约对象。

没有 update/delete：裁决是留痕，写错就再记一条，不能把历史改掉。同一个
``decision_id`` 重复落库会报 `ConflictError`（先查一次，主键约束再兜底并发）。

## dissent 保留不展示

回读必须带上 ``dissent``（模型评估要用），但任何展示层都不得渲染它——它是
"三份里被否掉的意见"，律师看裁决卡时只该看到结论与理由。本模块不提供
"公开视图"函数：展示层由 A9 负责，这里只保证数据不丢。
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.contract_review.services.write_contracts import Decision
from apps.core.exceptions import ConflictError, ValidationException

from .models import ContractDecision, DecisionOwnerKind, new_decision_id

OWNER_KINDS: frozenset[str] = frozenset(DecisionOwnerKind.values)


def record_decision(decision: Decision) -> Decision:
    """把裁决写进台账，返回**落库后**的契约对象（补全默认 id/时间）。"""

    normalized = _normalize(decision)
    if ContractDecision.objects.filter(pk=normalized.decision_id).exists():
        raise ConflictError(f"裁决 {normalized.decision_id} 已存在，裁决台账只追加不改写")
    try:
        with transaction.atomic():
            row = ContractDecision.objects.create(
                decision_id=normalized.decision_id,
                session_id=normalized.session_id,
                owner_kind=normalized.owner_kind,
                owner_id=normalized.owner_id,
                subpath=normalized.subpath,
                clause_key=normalized.clause_key,
                chosen_patch_id=normalized.chosen_patch_id,
                manual_text=normalized.manual_text,
                basis=normalized.basis,
                decided_by=normalized.decided_by,
                reason=normalized.reason,
                dissent=list(normalized.dissent),
                decided_at=normalized.decided_at,
            )
    except IntegrityError as exc:  # 同一 decision_id 重复落库 = 试图改历史
        raise ConflictError(f"裁决 {normalized.decision_id} 已存在，裁决台账只追加不改写") from exc
    return to_decision(row)


def load_decision(decision_id: str) -> Decision | None:
    """按 id 回读；不存在返回 ``None``（调用方自己决定报 404 还是当"未裁决"）。"""

    row = ContractDecision.objects.filter(pk=decision_id).first()
    return to_decision(row) if row is not None else None


def to_decision(row: ContractDecision) -> Decision:
    """存储行 → 冻结契约对象（``None`` 与空串的区别按契约保留）。"""

    return Decision(
        decision_id=row.decision_id,
        session_id=row.session_id,
        owner_kind=row.owner_kind,  # type: ignore[arg-type]  # choices 保证取值
        owner_id=row.owner_id,
        subpath=row.subpath,
        clause_key=row.clause_key,
        chosen_patch_id=row.chosen_patch_id,
        manual_text=row.manual_text,
        basis=dict(row.basis or {}),
        decided_by=row.decided_by,
        reason=row.reason,
        dissent=tuple(dict(item) for item in (row.dissent or ())),
        decided_at=row.decided_at,
    )


def _normalize(decision: Decision) -> Decision:
    """校验并补默认值；不合契约形状的输入在这里就拒绝，不落库。"""

    if not decision.decision_id:
        raise ValidationException("decision_id 不能为空")
    if decision.owner_kind not in OWNER_KINDS:
        raise ValidationException(f"owner_kind 非法：{decision.owner_kind!r}（只允许 {sorted(OWNER_KINDS)}）")
    if not decision.subpath:
        raise ValidationException("subpath 不能为空")
    if not isinstance(decision.basis, dict):
        raise ValidationException('basis 必须是 dict（{"citations": [...], "rubric_ids": [...]}）')

    dissent = tuple(decision.dissent)
    if not all(isinstance(item, dict) for item in dissent):
        raise ValidationException("dissent 必须是 dict 列表（少数意见的原样快照）")

    return Decision(
        decision_id=decision.decision_id,
        session_id=decision.session_id,
        owner_kind=decision.owner_kind,
        owner_id=decision.owner_id,
        subpath=decision.subpath,
        clause_key=decision.clause_key,
        chosen_patch_id=decision.chosen_patch_id,
        manual_text=decision.manual_text,
        basis=dict(decision.basis),
        decided_by=decision.decided_by,
        reason=decision.reason,
        dissent=dissent,
        decided_at=decision.decided_at or timezone.now(),
    )


__all__ = ["new_decision_id", "record_decision", "load_decision", "to_decision"]
