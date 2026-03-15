from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus

logger = logging.getLogger(__name__)


class ExecutorTaskLifecycleMixin:
    @staticmethod
    def _acquire_task(task_id: str) -> tuple[LegalResearchTask | None, dict[str, Any] | None]:
        now = timezone.now()
        updated = LegalResearchTask.objects.filter(
            id=task_id,
            status__in=[LegalResearchTaskStatus.PENDING, LegalResearchTaskStatus.QUEUED],
        ).update(
            status=LegalResearchTaskStatus.RUNNING,
            progress=0,
            error="",
            message="任务已启动",
            started_at=now,
            finished_at=None,
            updated_at=now,
        )

        task = (
            LegalResearchTask.objects.select_related("created_by", "credential", "credential__lawyer")
            .filter(id=task_id)
            .first()
        )
        if task is None:
            logger.error("案例检索任务不存在", extra={"task_id": task_id})
            return None, {"task_id": task_id, "status": "failed", "error": "任务不存在"}

        if updated == 1:
            return task, None

        if task.status in (
            LegalResearchTaskStatus.COMPLETED,
            LegalResearchTaskStatus.FAILED,
            LegalResearchTaskStatus.CANCELLED,
        ):
            return None, {"task_id": str(task.id), "status": task.status}

        if task.status == LegalResearchTaskStatus.RUNNING:
            return None, {"task_id": str(task.id), "status": task.status, "message": "任务已在执行中"}

        if task.status == LegalResearchTaskStatus.QUEUED:
            return None, {"task_id": str(task.id), "status": task.status, "message": "任务仍在排队中"}

        return None, {"task_id": str(task.id), "status": task.status, "message": "任务状态已变更，跳过本次执行"}

    @staticmethod
    def _mark_completed(task: LegalResearchTask, *, message: str) -> None:
        task.status = LegalResearchTaskStatus.COMPLETED
        task.progress = 100
        task.message = message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "progress", "message", "finished_at", "updated_at"])

    @staticmethod
    def _mark_failed(task: LegalResearchTask, error_message: str) -> None:
        task.status = LegalResearchTaskStatus.FAILED
        task.message = "任务执行失败"
        task.error = error_message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])

    @staticmethod
    def _is_cancel_requested(task_id: str | int) -> bool:
        status = LegalResearchTask.objects.filter(id=task_id).values_list("status", flat=True).first()
        return status == LegalResearchTaskStatus.CANCELLED

    @staticmethod
    def _mark_cancelled(*, task: LegalResearchTask, scanned: int, matched: int, skipped: int = 0) -> None:
        task.status = LegalResearchTaskStatus.CANCELLED
        task.scanned_count = scanned
        task.matched_count = matched
        skip_suffix = f"，跳过 {skipped}" if skipped else ""
        task.message = f"任务已取消，停止于扫描 {scanned}/{task.max_candidates}，命中 {matched}/{task.target_count}{skip_suffix}"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "scanned_count", "matched_count", "message", "finished_at", "updated_at"])

    @classmethod
    def _update_progress(cls, *, task: LegalResearchTask, scanned: int, matched: int, skipped: int = 0) -> None:
        total = max(task.max_candidates, 1)
        attempted = min(total, scanned + skipped)
        progress = min(95, int(attempted * 100 / total))
        task.scanned_count = scanned
        task.matched_count = matched
        task.progress = progress
        skip_suffix = f"，跳过 {skipped}" if skipped else ""
        task.message = (
            f"扫描 {scanned}/{task.max_candidates}，已获取候选 {task.candidate_count}，"
            f"命中 {matched}/{task.target_count}{skip_suffix}"
        )
        task.save(update_fields=["scanned_count", "matched_count", "progress", "message", "updated_at", "llm_model"])
