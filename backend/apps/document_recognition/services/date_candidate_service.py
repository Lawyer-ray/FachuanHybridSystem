"""日期候选服务

职责链：提取合并（LLM key_events + 正则候选）→ 落库为候选行 →
律师人工确认后写入重要日期提醒 → 撤销。

设计要点（评审定稿）：
- 幂等由候选行状态机承担：事务内 ``select_for_update`` 锁行，已 confirmed
  的行直接返回原 reminder_id；**不走** ``upsert_case_log_reminder_internal``
  （它按 case_log+source 定位只取一条，多日期会互相覆盖）。
- 未绑定案件的任务确认日期 → 创建**独立提醒**（无 case_log，metadata 带
  task 溯源），记一笔快捕获场景不强制选案。
- 存量自动写入的旧提醒无 metadata.source：确认前按
  ``(case_log_id, due_at)`` 查重复用，避免同一时间出现双提醒。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import ReminderType

from ._datetime_extraction_mixin import DatetimeExtractionMixin
from .data_classes import DocumentType

logger = logging.getLogger("apps.document_recognition")

REMINDER_SOURCE = "document_recognition"

# 类型展示优先级：开庭最关键，其次保全到期、举证、上诉……
REMINDER_TYPE_PRIORITY: dict[str, int] = {
    "hearing": 0,
    "asset_preservation_expires": 1,
    "evidence_deadline": 2,
    "appeal_deadline": 3,
    "payment_deadline": 4,
    "submission_deadline": 5,
    "statute_limitations": 6,
    "other": 7,
}

# 降级路径：上下文未命中类型关键词时按文书类型给默认
DEFAULT_TYPE_BY_DOCUMENT_TYPE: dict[DocumentType, str] = {
    DocumentType.SUMMONS: "hearing",
    DocumentType.EXECUTION_RULING: "asset_preservation_expires",
    DocumentType.OTHER: "other",
}

MAX_CANDIDATES = 8
STALE_DAYS = 180

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d")


@dataclass
class DateCandidateDraft:
    """合并后的日期候选（落库前的内存形态）。"""

    due_at: datetime
    reminder_type: str
    context_text: str
    source: str  # llm | regex | merged
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "due_at": self.due_at.isoformat(),
            "reminder_type": self.reminder_type,
            "context_text": self.context_text,
            "source": self.source,
            "confidence": self.confidence,
        }


class _RegexCandidateExtractor(DatetimeExtractionMixin):
    """仅用 Mixin 的纯函数能力，避免依赖 InfoExtractor 的 LLM 注入。"""


def parse_candidate_datetime(value: str) -> datetime | None:
    """解析 LLM/前端提交的日期时间字符串（统一返回 naive 本地时间）。"""
    from django.utils.timezone import localtime

    text = value.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    # 带时区偏移的输入（如 LLM 输出 +00:00）：先换算到本地时区再去 tzinfo，
    # 直接 replace 会把偏移量原样丢弃导致时间错位
    return localtime(parsed).replace(tzinfo=None)


def _normalize_aware(dt: datetime) -> datetime:
    """naive 本地时间补时区（与 reminders.validators.normalize_due_at 口径一致）。"""
    from django.utils.timezone import make_aware

    return dt if dt.tzinfo else make_aware(dt)


def build_date_candidates(
    text: str,
    analysis: Any | None,
    document_type: DocumentType,
    *,
    regex_extractor: Any | None = None,
) -> list[DateCandidateDraft]:
    """合并 LLM key_events 与正则候选为去重后的候选列表。

    去重键 = (日期时间, 提醒类型)：同值 LLM 优先（source 升级为 merged、
    置信度取 max）；同日不同类型都保留（开庭日与举证截止同日是真实场景）。
    """
    extractor = regex_extractor or _RegexCandidateExtractor()
    default_type = DEFAULT_TYPE_BY_DOCUMENT_TYPE.get(document_type, "other")

    drafts: dict[tuple[datetime, str], DateCandidateDraft] = {}

    # 1. LLM 事件
    key_events = list(getattr(analysis, "key_events", None) or [])
    for event in key_events:
        parsed = parse_candidate_datetime(str(getattr(event, "datetime", "") or ""))
        if parsed is None:
            logger.warning("LLM 日期事件解析失败，跳过: %s", getattr(event, "datetime", None))
            continue
        event_type = getattr(event, "event_type", "other") or "other"
        if event_type not in ReminderType.values:
            event_type = "other"
        context = str(getattr(event, "context", "") or "")[:255]
        drafts[(parsed, event_type)] = DateCandidateDraft(
            due_at=parsed,
            reminder_type=event_type,
            context_text=context,
            source="llm",
            confidence=float(getattr(event, "confidence", 0.7) or 0.7),
        )

    # 2. 正则候选（透出全部，含上下文与类型推断）
    for candidate in extractor.extract_datetime_candidates(text):
        parsed = candidate["datetime"]
        reminder_type = candidate.get("reminder_type") or default_type
        key = (parsed, reminder_type)
        regex_confidence = round(min(float(candidate.get("context_score", 0)), 100) / 100 * 0.85, 2)
        existing = drafts.get(key)
        if existing is None:
            drafts[key] = DateCandidateDraft(
                due_at=parsed,
                reminder_type=reminder_type,
                context_text=str(candidate.get("context_text", ""))[:255],
                source="regex",
                confidence=regex_confidence,
            )
        else:
            existing.source = "merged"
            existing.confidence = max(existing.confidence, regex_confidence)
            if not existing.context_text:
                existing.context_text = str(candidate.get("context_text", ""))[:255]

    # 3. 陈旧候选降置信（改判文书可能含历史日期，折叠而非丢弃）
    today = timezone.localdate()
    for draft in drafts.values():
        if (today - draft.due_at.date()).days > STALE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)

    ordered = sorted(
        drafts.values(),
        key=lambda d: (REMINDER_TYPE_PRIORITY.get(d.reminder_type, 99), -d.confidence, d.due_at),
    )
    return ordered[:MAX_CANDIDATES]


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


def list_candidates(task: Any) -> list[dict[str, Any]]:
    """候选行序列化（API/admin 共用）。"""
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
        }
        for row in task.date_candidates.select_related("reminder").order_by("due_at", "id")
    ]


def _reminder_type_label(reminder_type: str) -> str:
    try:
        return str(ReminderType(reminder_type).label)
    except ValueError:
        return reminder_type


def _resolve_reminder_service() -> Any:
    from apps.reminders.services.wiring import get_reminder_service

    return get_reminder_service()


def _build_reminder_content(reminder_type: str, context_text: str) -> str:
    label = _reminder_type_label(reminder_type)
    snippet = (context_text or "").strip()[:60]
    return f"{label}：{snippet}" if snippet else label


@transaction.atomic
def confirm_candidates(task_id: int, items: list[dict[str, Any]], user: Any | None = None) -> list[dict[str, Any]]:
    """批量确认/忽略日期候选，逐项返回结果。

    每项: {candidate_id, action: confirm|skip, due_at?, reminder_type?}。
    幂等：已 confirmed 的候选直接返回原 reminder_id。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionStatus, DocumentRecognitionTask

    task = DocumentRecognitionTask.objects.select_for_update().get(id=task_id)
    if task.status != DocumentRecognitionStatus.SUCCESS:
        raise ValidationException(
            message="任务尚未识别完成，不能确认日期",
            code="TASK_NOT_READY",
            errors={},
        )

    user_id = getattr(user, "id", None) if user else None
    reminder_service = _resolve_reminder_service()
    now = timezone.now()
    results: list[dict[str, Any]] = []

    candidate_ids = [item["candidate_id"] for item in items]
    locked_rows = {row.id: row for row in task.date_candidates.select_for_update().filter(id__in=candidate_ids)}

    for item in items:
        results.append(
            _confirm_single_item(
                task=task,
                item=item,
                row=locked_rows.get(item["candidate_id"]),
                reminder_service=reminder_service,
                user_id=user_id,
                now=now,
            )
        )

    refresh_task_confirmation_status(task)
    return results


def _confirm_single_item(
    *,
    task: Any,
    item: dict[str, Any],
    row: Any | None,
    reminder_service: Any,
    user_id: int | None,
    now: datetime,
) -> dict[str, Any]:
    from apps.document_recognition.models import DateCandidateStatus

    candidate_id = item["candidate_id"]
    action = item.get("action", "confirm")

    if row is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "候选不存在",
            "error_code": "CANDIDATE_NOT_FOUND",
        }

    if action == "skip":
        if row.status == DateCandidateStatus.CONFIRMED:
            return {
                "candidate_id": candidate_id,
                "status": "confirmed",
                "reminder_id": row.reminder_id,
                "message": "候选已确认过提醒，忽略无效",
                "error_code": None,
            }
        row.status = DateCandidateStatus.SKIPPED
        row.save(update_fields=["status", "updated_at"])
        return {
            "candidate_id": candidate_id,
            "status": "skipped",
            "reminder_id": None,
            "message": "已忽略",
            "error_code": None,
        }

    # action == confirm
    if row.status == DateCandidateStatus.CONFIRMED and row.reminder_id:
        return {
            "candidate_id": candidate_id,
            "status": "confirmed",
            "reminder_id": row.reminder_id,
            "message": "已确认过，幂等返回",
            "error_code": None,
        }

    due_at_raw = item.get("due_at") or row.due_at.isoformat()
    parsed = parse_candidate_datetime(str(due_at_raw)) if isinstance(due_at_raw, str) else due_at_raw
    if parsed is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "时间格式不正确",
            "error_code": "INVALID_TIME_FORMAT",
        }
    aware_due_at = _normalize_aware(parsed)

    reminder_type = item.get("reminder_type") or row.reminder_type
    if reminder_type not in ReminderType.values:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": f"不支持的提醒类型: {reminder_type}",
            "error_code": "INVALID_REMINDER_TYPE",
        }

    message = "已写入提醒"
    reminder = _find_existing_reminder(reminder_service, task, aware_due_at)
    if reminder is not None:
        message = "复用了同时间点的既有提醒，未重复创建"
    else:
        reminder = reminder_service.create_reminder(
            case_log_id=task.case_log_id,
            reminder_type=reminder_type,
            content=_build_reminder_content(reminder_type, row.context_text),
            due_at=aware_due_at,
            metadata={
                "source": REMINDER_SOURCE,
                "source_id": f"task:{task.id}:candidate:{row.id}",
                "task_id": task.id,
            },
        )
        # 确认过的重要日期默认列入案件「重要时间」视图（服务层无该参数，落实例后补写）
        reminder.include_in_important_time = True
        reminder.save(update_fields=["include_in_important_time"])

    row.due_at = aware_due_at
    row.reminder_type = reminder_type
    row.status = DateCandidateStatus.CONFIRMED
    row.reminder_id = reminder.id
    row.confirmed_by_id = user_id
    row.confirmed_at = now
    row.save(
        update_fields=[
            "due_at",
            "reminder_type",
            "status",
            "reminder_id",
            "confirmed_by_id",
            "confirmed_at",
            "updated_at",
        ]
    )

    logger.info(
        "日期候选已确认: task_id=%s, candidate_id=%s, reminder_id=%s, standalone=%s",
        task.id,
        candidate_id,
        reminder.id,
        task.case_log_id is None,
    )
    return {
        "candidate_id": candidate_id,
        "status": "confirmed",
        "reminder_id": reminder.id,
        "message": message,
        "error_code": None,
    }


def _find_existing_reminder(reminder_service: Any, task: Any, aware_due_at: datetime) -> Any | None:
    """按 (case_log_id, due_at) 查重复用（含无 source 的旧自动提醒）；独立提醒无查重域。"""
    if task.case_log_id is None:
        return None
    existing = reminder_service.list_reminders(case_log_id=task.case_log_id)
    for reminder in existing:
        if reminder.due_at == aware_due_at:
            return reminder
    return None


@transaction.atomic
def revoke_confirmation(task_id: int, candidate_id: int) -> dict[str, Any]:
    """撤销确认：删除本功能创建的提醒，候选行回到待确认。"""
    from apps.document_recognition.models import (
        DateCandidateStatus,
        DocumentRecognitionDateCandidate,
        DocumentRecognitionTask,
    )

    task = DocumentRecognitionTask.objects.select_for_update().get(id=task_id)
    try:
        row = task.date_candidates.select_for_update().get(id=candidate_id)
    except DocumentRecognitionDateCandidate.DoesNotExist:
        raise NotFoundError(message="候选不存在", code="CANDIDATE_NOT_FOUND", errors={}) from None

    if row.status != DateCandidateStatus.CONFIRMED:
        raise ValidationException(message="候选未确认，无需撤销", code="NOT_CONFIRMED", errors={})

    if row.reminder_id:
        reminder_service = _resolve_reminder_service()
        reminder = reminder_service.get_reminder(row.reminder_id)
        metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
        if metadata.get("source") != REMINDER_SOURCE:
            raise ValidationException(
                message="该提醒不是文书识别创建的，不能在此撤销",
                code="NOT_REVOKABLE",
                errors={},
            )
        reminder_service.delete_reminder(reminder.id)

    row.status = DateCandidateStatus.PENDING
    row.reminder_id = None
    row.confirmed_by_id = None
    row.confirmed_at = None
    row.save(update_fields=["status", "reminder_id", "confirmed_by_id", "confirmed_at", "updated_at"])
    refresh_task_confirmation_status(task)

    logger.info("日期候选已撤销: task_id=%s, candidate_id=%s", task_id, candidate_id)
    return {
        "candidate_id": candidate_id,
        "status": "pending",
        "reminder_id": None,
        "message": "已撤销并删除提醒",
        "error_code": None,
    }
