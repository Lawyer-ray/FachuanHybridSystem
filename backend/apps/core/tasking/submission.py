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
