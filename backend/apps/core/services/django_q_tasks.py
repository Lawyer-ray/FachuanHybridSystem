"""Business logic services."""

from typing import Any, cast


def submit_q_task(func: str, *args: Any, task_name: str | None = None, **kwargs: Any) -> str:
    from django_q.tasks import async_task

    return cast(str, async_task(func, *args, task_name=task_name, **kwargs))


def get_q_task_status(task_id: str) -> dict[str, Any]:
    from django_q.models import OrmQ, Task

    task = Task.objects.filter(id=task_id).first()
    if task:
        return {
            "task_id": task_id,
            "status": "success" if task.success else "failure",
            "result": task.result,
            "started_at": task.started.isoformat() if task.started else None,
            "finished_at": task.stopped.isoformat() if task.stopped else None,
        }

    queued = OrmQ.objects.filter(key=task_id).exists()
    if queued:
        return {"task_id": task_id, "status": "pending", "result": None, "started_at": None, "finished_at": None}

    return {"task_id": task_id, "status": "not_found", "result": None, "started_at": None, "finished_at": None}
