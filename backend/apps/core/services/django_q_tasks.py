"""任务提交与查询的向后兼容入口。

新代码应直接使用 ``apps.core.tasking`` 中的 submit_task / TaskQueryService。
本模块仅为存量调用方保留，避免一次性改全量。
"""

from __future__ import annotations

from typing import Any


def submit_q_task(func: str, *args: Any, task_name: str | None = None, **kwargs: Any) -> str:
    from apps.core.tasking import submit_task

    return submit_task(func, *args, task_name=task_name, kwargs=kwargs if kwargs else None)


def get_q_task_status(task_id: str) -> dict[str, Any]:
    from apps.core.tasking import TaskQueryService

    return TaskQueryService().get_task_status(task_id)
