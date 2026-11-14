"""关键日期捕获服务（法院短信 → 记一笔的「旁线」入口）。

**定位：法院短信主线的旁支，绝不反向影响主线。**

前端法院短信弹窗打开一条已完成的短信时调用本服务：把这条短信已归档的每份文书
自动送去文书识别，识别只产出「关键日期候选」，等律师确认后才写入日历（提醒）。
整条链路与法院短信状态机完全解耦——识别失败/超时/卡住都不会改变 CourtSMS
的任何状态字段；短信侧不转账、不建日志、不发通知（见 apps/document_recognition/tasks.py）。

复用而不是重算：
- 案件 / 案件日志直接采用短信第一轮绑定的结果（`prebound_case_id/case_log_id`），
  识别期不再匹配案件、不重命名、不建日志、不重复通知；
- 案号优先用短信正文解析结果（`known_case_number`），当事人/类型在识别无果时兜底。

幂等键 = (来源短信, 来源文书路径)：
- 同一份文书已有 pending/processing/success 任务 → 直接复用，不重复烧 LLM；
- 已有 failed 任务 → 原地重跑（复用已落库文件，不重新读盘建行）；
- `force=True` → 无条件新建一个任务（「重新识别」按钮用，旧任务保留可回看）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.document_recognition")


@dataclass
class DateCaptureSource:
    """来源管线（法院短信）提供的上下文，全部为纯数据、不含模型对象。

    刻意不让本服务 import automation 的模型：短信侧只管把 DTO 递过来，
    日期旁线的失败不会让短信侧出现任何 import/装配层面的耦合。
    """

    sms_id: int
    case_id: int | None
    case_log_id: int | None
    document_paths: list[str] = field(default_factory=list)


@dataclass
class DateCaptureItem:
    """单份文书的送识别结果。"""

    document_path: str
    document_name: str
    task_id: int | None
    status: str
    action: str  # reused / retried / created / skipped
    candidate_count: int = 0
    pending_count: int = 0
    date_confirmation_status: str | None = None
    error_message: str = ""
    reason: str = ""


def capture_dates_for_source(
    source: DateCaptureSource,
    *,
    user: Any | None = None,
    force: bool = False,
    llm_model: str | None = None,
) -> list[DateCaptureItem]:
    """把来源短信的每份文书送去识别（幂等），返回逐份结果。

    不抛业务异常给调用方：单份文书的任何失败都只是该行的 error 字段，
    其余文书继续送——一条短信里有一份坏文件不该拖垮整批。
    """
    if not source.document_paths:
        return [
            DateCaptureItem(
                document_path="",
                document_name="",
                task_id=None,
                status="skipped",
                action="skipped",
                reason="该短信没有可识别的文书（通知类短信，或文书尚未下载成功）",
            )
        ]
    if not source.case_log_id:
        return [
            DateCaptureItem(
                document_path="",
                document_name="",
                task_id=None,
                status="skipped",
                action="skipped",
                reason="短信尚未绑定案件（无案件日志），无法确定日期归属",
            )
        ]

    return [
        _capture_one(source, raw_path, user=user, force=force, llm_model=llm_model)
        for raw_path in source.document_paths
    ]


def list_source_tasks(source_court_sms_id: int, *, user: Any | None = None) -> list[dict[str, Any]]:
    """来源短信派生出的全部识别任务（按创建顺序），供短信详情摘要与「继续确认」入口。"""
    from apps.document_recognition.models import DocumentRecognitionTask
    from apps.document_recognition.services.task_service import task_ownership_q

    qs = DocumentRecognitionTask.objects.filter(source_court_sms_id=source_court_sms_id)
    ownership = task_ownership_q(user)
    if ownership is not None:
        qs = qs.filter(ownership)

    rows: list[dict[str, Any]] = []
    for task in qs.order_by("id"):
        counts = _candidate_counts(task)
        rows.append(
            {
                "task_id": int(task.id),
                "document_path": task.source_document_path or task.file_path,
                "document_name": Path(task.source_document_path or task.file_path).name,
                "status": str(task.status),
                "error_message": task.error_message or "",
                "classification_hint": task.classification_hint or "",
                "document_type": task.document_type or "",
                "case_number": task.case_number or "",
                "candidate_count": sum(counts.values()),
                "pending_count": counts["pending"],
                "confirmed_count": counts["confirmed"],
                "skipped_count": counts["skipped"],
                "date_confirmation_status": str(task.date_confirmation_status or ""),
            }
        )
    return rows


def _capture_one(
    source: DateCaptureSource,
    raw_path: str,
    *,
    user: Any | None,
    force: bool,
    llm_model: str | None,
) -> DateCaptureItem:
    from apps.document_recognition.models import DocumentRecognitionStatus, DocumentRecognitionTask

    name = Path(raw_path).name if raw_path else ""
    if not raw_path or not Path(raw_path).exists():
        return DateCaptureItem(
            document_path=raw_path,
            document_name=name,
            task_id=None,
            status="skipped",
            action="skipped",
            reason="文书文件已不在磁盘上（可能被清理或移动）",
        )

    existing = (
        DocumentRecognitionTask.objects.filter(
            source_court_sms_id=source.sms_id,
            source_document_path=raw_path,
        )
        .order_by("-id")
        .first()
    )

    if existing is not None and not force:
        if str(existing.status) == DocumentRecognitionStatus.FAILED:
            return _restart_existing(existing)
        return _reuse_existing(existing)

    try:
        task = _create_task(source, raw_path=raw_path, user=user, llm_model=llm_model)
    except Exception as exc:  # pragma: no cover - 建任务失败只影响本行
        logger.exception("送识别失败: sms=%s, path=%s", source.sms_id, raw_path)
        return DateCaptureItem(
            document_path=raw_path,
            document_name=name,
            task_id=None,
            status="skipped",
            action="skipped",
            reason=f"创建识别任务失败: {exc}",
        )

    return DateCaptureItem(
        document_path=raw_path,
        document_name=name,
        task_id=int(task.id),
        status=str(task.status),
        action="created",
    )


def _reuse_existing(task: Any) -> DateCaptureItem:
    """复用存量任务（在跑 / 已成功），顺带把候选数带回去给前端显示。"""
    counts = _candidate_counts(task)
    path = task.source_document_path or task.file_path
    return DateCaptureItem(
        document_path=path,
        document_name=Path(path).name,
        task_id=int(task.id),
        status=str(task.status),
        action="reused",
        candidate_count=sum(counts.values()),
        pending_count=counts["pending"],
        date_confirmation_status=str(task.date_confirmation_status or ""),
    )


def _restart_existing(task: Any) -> DateCaptureItem:
    """失败的存量任务就地重跑（复用已落库文件，不新建行、不重新读盘）。"""
    from apps.document_recognition.models import DocumentRecognitionStatus

    path = task.source_document_path or task.file_path
    name = Path(path).name
    reset_error = ""
    try:
        task.status = DocumentRecognitionStatus.PENDING
        task.error_message = ""
        task.started_at = None
        task.finished_at = None
        task.save(update_fields=["status", "error_message", "started_at", "finished_at"])
        _submit(str(task.id))
    except Exception as exc:  # pragma: no cover - 重跑失败只影响本行
        logger.exception("重跑识别失败: task=%s", task.id)
        reset_error = f"重跑识别失败: {exc}"

    counts = _candidate_counts(task)
    return DateCaptureItem(
        document_path=path,
        document_name=name,
        task_id=int(task.id),
        status=str(task.status),
        action="retried",
        candidate_count=sum(counts.values()),
        pending_count=counts["pending"],
        date_confirmation_status=str(task.date_confirmation_status or ""),
        error_message=reset_error,
    )


def _create_task(
    source: DateCaptureSource,
    *,
    raw_path: str,
    user: Any | None,
    llm_model: str | None,
) -> Any:
    """建识别任务并投递异步执行（与上传接口同一条 worker 路径）。"""
    from apps.document_recognition.services.task_service import DocumentRecognitionTaskService

    task = DocumentRecognitionTaskService().create_task(
        file_path=raw_path,
        original_filename=Path(raw_path).name,
        source_court_sms_id=source.sms_id,
        source_document_path=raw_path,
        case_id=source.case_id,
        case_log_id=source.case_log_id,
        llm_model=llm_model,
        created_by=user,
    )
    _submit(str(task.id))
    return task


def _submit(task_id: str) -> None:
    from apps.core.tasking import submit_task

    submit_task(
        "apps.document_recognition.tasks.execute_document_recognition_task",
        int(task_id),
        task_name=f"document_recognition_{task_id}",
        timeout=600,
    )


def _candidate_counts(task: Any) -> dict[str, int]:
    """任务下候选行的按状态计数（前端/短信详情摘要用）。"""
    counts = {"pending": 0, "confirmed": 0, "skipped": 0}
    for row_status in task.date_candidates.values_list("status", flat=True):
        counts[row_status] = counts.get(row_status, 0) + 1
    return counts
