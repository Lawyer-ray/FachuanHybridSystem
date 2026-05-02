from __future__ import annotations

from django.utils import timezone

from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus


def sync_failed_queue_state(
    *,
    task: LegalResearchTask,
    failed_message: str = "任务执行失败（队列状态自动回填）",
) -> bool:
    if task.status not in {LegalResearchTaskStatus.QUEUED, LegalResearchTaskStatus.RUNNING}:
        return False
    if not task.q_task_id:
        return False

    try:
        from apps.core.tasking import TaskQueryService

        q_task_info = TaskQueryService().get_failed_task_info(task.q_task_id)
    except Exception:
        return False

    if q_task_info is None:
        return False

    error_text = str(q_task_info.get("result") or "").strip()
    if len(error_text) > 1000:
        error_text = error_text[:1000]

    task.status = LegalResearchTaskStatus.FAILED
    task.message = failed_message
    task.error = error_text or task.error
    task.finished_at = task.finished_at or q_task_info.get("stopped") or timezone.now()
    task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
    return True
