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
        from django_q.models import Task as DjangoQTask
    except Exception:
        return False

    q_task = DjangoQTask.objects.filter(id=task.q_task_id).only("success", "stopped", "result").first()
    if q_task is None or q_task.stopped is None or q_task.success:
        return False

    error_text = str(q_task.result or "").strip()
    if len(error_text) > 1000:
        error_text = error_text[:1000]

    task.status = LegalResearchTaskStatus.FAILED
    task.message = failed_message
    task.error = error_text or task.error
    task.finished_at = task.finished_at or q_task.stopped or timezone.now()
    task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
    return True
