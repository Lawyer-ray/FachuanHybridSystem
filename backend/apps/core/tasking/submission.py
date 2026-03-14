"""Module for submission."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

from .context import TaskContext, get_current_request_id


class TaskSubmissionService:
    def submit(
        self,
        target: str,
        *,
        args: Sequence[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        task_name: str | None = None,
        timeout: Any | None = None,
        group: str | None = None,
        hook: Any | None = None,
        context: TaskContext | None = None,
        cached: Any | None = None,
        sync: Any | None = None,
        save: Any | None = None,
        broker: Any | None = None,
        cluster: Any | None = None,
        ack_failure: Any | None = None,
        q_options: Any | None = None,
    ) -> str:
        from django_q.tasks import async_task

        base_request_id = get_current_request_id()
        ctx = context or TaskContext()
        if not ctx.request_id and base_request_id:
            ctx = replace(ctx, request_id=base_request_id)
        if task_name and not ctx.task_name:
            ctx = replace(ctx, task_name=task_name)

        return cast(
            str,
            async_task(
                "apps.core.tasking.entries.run_task",
                target,
                list(args or []),
                kwargs or {},
                ctx.to_dict(),
                task_name=task_name,
                timeout=timeout,
                group=group,
                hook=hook,
                cached=cached,
                sync=sync,
                save=save,
                broker=broker,
                cluster=cluster,
                ack_failure=ack_failure,
                q_options=q_options,
            ),
        )

    def cancel(self, task_id: str) -> dict[str, Any]:
        """Best-effort cancellation for a Django-Q task id.

        - Queued tasks can be removed from OrmQ.
        - Running tasks cannot be force-killed here; caller should use cooperative
          cancellation in business logic.
        """
        from django_q.models import OrmQ, Task

        queue_deleted, _ = OrmQ.objects.filter(key=task_id).delete()
        task = Task.objects.filter(id=task_id).first()

        running = bool(task and task.started and not task.stopped)
        finished = bool(task and task.stopped)
        return {
            "task_id": task_id,
            "queue_deleted": int(queue_deleted),
            "running": running,
            "finished": finished,
            "exists": task is not None,
        }
