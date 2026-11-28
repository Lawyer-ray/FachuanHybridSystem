"""日期候选的落库与序列化层（从 ``date_candidate_service`` 拆分出来，2026-11-27）。

承载**会碰 ORM** 的那几段：候选行落库（``persist_candidates``）、任务级确认进度
刷新（``refresh_task_confirmation_status``）、批内去重（``reconcile_source_candidates``）、
序列化（``list_candidates``）与任务行锁取用（``_get_task_for_update``）。

依赖方向单向：``date_candidate_service`` → 本模块 → ``date_candidate_rules``。
本模块**不得** import ``date_candidate_service``（会成环）。行为与原模块逐字一致。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.exceptions import NotFoundError

from .date_candidate_policy import (
    DERIVATION_LABELS,
    FLAG_DUPLICATE,
    FLAG_GENERIC_BOILERPLATE,
    AnchorKind,
    anchor_note_for,
)
from .date_candidate_rules import DateCandidateDraft, _normalize_aware, _reminder_type_label

logger = logging.getLogger("apps.document_recognition")


def persist_candidates(task: Any, drafts: list[DateCandidateDraft]) -> int:
    """把候选草稿落库为候选行（任务已有候选时跳过，保证幂等）。"""
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionDateCandidate

    if task.date_candidates.exists():
        return 0

    rows = [
        DocumentRecognitionDateCandidate(
            task=task,
            due_at=_normalize_aware(draft.due_at),
            reminder_type=draft.reminder_type,
            context_text=draft.context_text,
            source=draft.source,
            confidence=draft.confidence,
            anchor_kind=draft.anchor_kind,
            anchor_at=draft.anchor_at,
            anchor_document=draft.anchor_document,
            derivation=draft.derivation,
            review_flags=list(draft.review_flags),
            default_checked=draft.default_checked,
            status=DateCandidateStatus.PENDING,
        )
        for draft in drafts
    ]
    DocumentRecognitionDateCandidate.objects.bulk_create(rows)
    refresh_task_confirmation_status(task)
    logger.info("日期候选已落库: task_id=%s, count=%d", task.id, len(rows))
    return len(rows)


def refresh_task_confirmation_status(task: Any) -> None:
    """按候选行状态刷新任务级日期确认进度（冗余字段，供筛选与侧栏）。"""
    from apps.document_recognition.models import DateConfirmationStatus

    counts = {"pending": 0, "confirmed": 0, "skipped": 0}
    for row in task.date_candidates.values_list("status", flat=True):
        counts[row] = counts.get(row, 0) + 1

    total = sum(counts.values())
    if total == 0:
        new_status = DateConfirmationStatus.NONE
    elif counts["pending"] == 0:
        new_status = DateConfirmationStatus.COMPLETE
    elif counts["confirmed"] + counts["skipped"] > 0:
        new_status = DateConfirmationStatus.PARTIAL
    else:
        new_status = DateConfirmationStatus.PENDING

    if task.date_confirmation_status != new_status:
        task.date_confirmation_status = new_status
        task.save(update_fields=["date_confirmation_status"])


#: 推算方式的权威度（越小越权威）：LLM 读到的原文日期 > 正则明文日期 > 相对期限推算 > 期间推算
_DERIVATION_AUTHORITY: dict[str, int] = {
    "llm_absolute": 0,
    "rule_absolute": 1,
    "rule_relative": 2,
    "rule_period": 3,
}


def reconcile_source_candidates(source_court_sms_id: int) -> int:
    """批内去重：一条法院短信的多份文书常报出同一天同一类型的期限。

    真实场景（2026-11-24）：《诉讼费退费缴费须知》与《诉讼费用交费通知书》
    都指向「12-01 前交受理费」——须知里的那句只是复述交费通知书的规则，
    真期限由交费通知书自己报。两条都留在确认弹窗里，律师无法判断该勾哪一条。

    口径（业务 2026-11-24 拍板）：
    - **只收敛"完全相同键"**：同一案件 + 同一天 + 同一提醒类型；
    - **同类型但日期不同、同日不同类型一律都留**——不做冲突裁决，因为
      冲突本身（两份文书各说一个日期）就是律师必须立刻知道的信息；
    - 权威度排序：非通用文书 > 通用文书；llm_absolute > rule_absolute >
      rule_relative > rule_period；同类取 context 更长者；再不行取小 id。

    幂等：只动 ``pending`` 行，已确认/已忽略的一律不碰；可反复调用。

    Returns:
        本次被折叠掉的行数。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionTask

    tasks = list(
        DocumentRecognitionTask.objects.filter(source_court_sms_id=source_court_sms_id).prefetch_related(
            "date_candidates"
        )
    )
    if not tasks:
        return 0

    # 复活孤儿：被折叠过的行若权威行已被删（duplicate_of SET_NULL），它不该永远消失
    for task in tasks:
        for row in task.date_candidates.all():
            if (
                row.status == DateCandidateStatus.SKIPPED
                and row.duplicate_of_id is None
                and FLAG_DUPLICATE in (row.review_flags or [])
            ):
                row.status = DateCandidateStatus.PENDING
                row.review_flags = [f for f in (row.review_flags or []) if f != FLAG_DUPLICATE]
                row.save(update_fields=["status", "review_flags", "updated_at"])
                logger.info("恢复孤儿候选: candidate=%s（权威行已不存在）", row.id)

    groups: dict[tuple[Any, Any, str], list[tuple[Any, Any]]] = {}
    for task in tasks:
        for row in task.date_candidates.all():
            if row.status != DateCandidateStatus.PENDING or row.duplicate_of_id:
                continue
            key = (task.case_id, row.due_at.date(), row.reminder_type)
            groups.setdefault(key, []).append((task, row))

    folded = 0
    touched: set[int] = set()
    for items in groups.values():
        if len(items) < 2:
            continue
        # 只折**跨任务**的重复：同一份文书里两条同类型同日期（如交费通知书把受理费与
        # 保全费都写成"七日内"）是两条不同的义务，折掉一条就等于漏一条。
        task_ids = {task.id for task, _row in items}
        if len(task_ids) < 2:
            continue
        items.sort(
            key=lambda pair: (
                1 if FLAG_GENERIC_BOILERPLATE in (pair[1].review_flags or []) else 0,
                _DERIVATION_AUTHORITY.get(pair[1].derivation, 9),
                -len(pair[1].context_text or ""),
                pair[1].id,
            )
        )
        winner_task, winner = items[0]
        for task, row in items[1:]:
            row.duplicate_of = winner
            row.status = DateCandidateStatus.SKIPPED
            flags = list(row.review_flags or [])
            if FLAG_DUPLICATE not in flags:
                flags.append(FLAG_DUPLICATE)
            row.review_flags = flags
            row.default_checked = False
            row.save(update_fields=["duplicate_of", "status", "review_flags", "default_checked", "updated_at"])
            folded += 1
            touched.add(task.id)
            logger.info(
                "批内去重折叠: task=%s candidate=%s (%s) → 权威 candidate=%s (task=%s)",
                task.id,
                row.id,
                row.due_at.date(),
                winner.id,
                winner_task.id,
            )

    for task in tasks:
        if task.id in touched:
            refresh_task_confirmation_status(task)
    return folded


def list_candidates(task: Any) -> list[dict[str, Any]]:
    """候选行序列化（API/admin 共用）。

    除了日期与类型，必须把**出处**一并透出：律师要靠「来源 + 起算点」判断
    这条日期靠不靠得住；旧实现算好了 anchor_note 却在落库前丢掉，前端从来没显示过。
    """
    return [
        {
            "id": row.id,
            "due_at": row.due_at.isoformat(),
            "reminder_type": row.reminder_type,
            "reminder_type_label": _reminder_type_label(row.reminder_type),
            "context_text": row.context_text,
            "source": row.source,
            "confidence": row.confidence,
            "status": row.status,
            "reminder_id": row.reminder_id,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "anchor_kind": row.anchor_kind,
            "anchor_at": row.anchor_at.isoformat() if row.anchor_at else None,
            "anchor_document": row.anchor_document,
            "derivation": row.derivation,
            "derivation_label": DERIVATION_LABELS.get(row.derivation, ""),
            "review_flags": list(row.review_flags or []),
            "default_checked": bool(row.default_checked),
            "anchor_note": _anchor_note_for_row(row),
            "duplicate_of_id": row.duplicate_of_id,
        }
        for row in task.date_candidates.select_related("reminder").order_by("due_at", "id")
    ]


def _anchor_note_for_row(row: Any) -> str:
    """按行上存的锚类型即时渲染「起算点」文案（不在库里存冗余文案）。"""
    try:
        kind = AnchorKind(row.anchor_kind) if row.anchor_kind else AnchorKind.UNKNOWN
    except ValueError:
        return ""
    if kind is AnchorKind.UNKNOWN and row.derivation in ("llm_absolute", "rule_absolute"):
        return "原文写明，无需推算"
    anchor_at = row.anchor_at
    days = (row.due_at.date() - anchor_at).days if anchor_at else None
    return anchor_note_for(kind=kind, anchor_at=anchor_at, delivery_date=None, days=days)


def _get_task_for_update(task_id: int, user: Any | None) -> Any:
    """行锁取任务并套归属口径（审计 P1 修复）。

    归属过滤并入同一次 ``.get()``（保持 ``select_for_update().get()`` 调用链，
    不破坏行锁防并发语义）；管理员见全量，普通用户见自己的任务与存量 NULL
    任务（兼容旧数据口径，详见 task_service.task_ownership_q）。
    非归属人非管理员与任务不存在同样抛 NotFoundError（404，不泄露存在性）。
    """
    from apps.document_recognition.models import DocumentRecognitionTask
    from apps.document_recognition.services.task_service import task_ownership_q

    qs = DocumentRecognitionTask.objects.select_for_update()
    ownership = task_ownership_q(user)
    try:
        if ownership is None:
            return qs.get(id=task_id)
        return qs.get(ownership, id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        raise NotFoundError(message="任务不存在", code="TASK_NOT_FOUND", errors={}) from None
