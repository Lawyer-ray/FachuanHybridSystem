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

        task_kwargs: dict[str, Any] = {
            "task_name": task_name,
            "group": group,
            "hook": hook,
            "cached": cached,
            "sync": sync,
            "save": save,
            "broker": broker,
            "cluster": cluster,
            "ack_failure": ack_failure,
        }
        if timeout is not None:
            task_kwargs["timeout"] = timeout
        if q_options is not None:
            if isinstance(q_options, dict):
                normalized_q_options = {k: v for k, v in q_options.items() if v is not None}
                if normalized_q_options:
                    task_kwargs["q_options"] = normalized_q_options
            else:
                task_kwargs["q_options"] = q_options
        task_kwargs = {k: v for k, v in task_kwargs.items() if v is not None}

        return cast(
            str,
            async_task(
                "apps.core.tasking.entries.run_task",
                target,
                list(args or []),
                kwargs or {},
                ctx.to_dict(),
                **task_kwargs,
            ),
        )

    def cancel(self, task_id: str) -> dict[str, Any]:
        """Best-effort cancellation for a Django-Q task id.

        - Queued tasks can be removed from OrmQ.
        - Running tasks cannot be force-killed here; caller should use cooperative
          cancellation in business logic.
        """
        from django_q.brokers import get_broker
        from django_q.models import OrmQ, Task

        queue_deleted, _ = OrmQ.objects.filter(key=task_id).delete()
        task = Task.objects.filter(id=task_id).first()

        running = bool(task and task.started and not task.stopped)
        finished = bool(task and task.stopped)
        # S20-01（2026-11-23 二轮审计）：`OrmQ` 只覆盖 **ORM broker**。配 Redis broker 时
        # 排队中的任务不在 OrmQ 里，`queue_deleted` 恒 0、`running` 也因还没有 Task 行而恒 False，
        # 调用方按 `not running` 判定就会把作业标成 CANCELLED —— 而任务其实还在 Redis 队列里，
        # 稍后照常执行（「取消了却还在跑」）。
        # 这里额外给出 `dequeued`：**只有能确认它不会再跑**时才是 True（出队成功或已结束）；
        # Redis broker 下没有可靠的单条出队 API，因此如实返回 False，调用方据此不要谎报已取消。
        broker_name = type(get_broker()).__name__
        dequeued = bool(queue_deleted) or finished
        return {
            "task_id": task_id,
            "queue_deleted": int(queue_deleted),
            "running": running,
            "finished": finished,
            "exists": task is not None,
            "broker": broker_name,
            "dequeued": dequeued,
        }
