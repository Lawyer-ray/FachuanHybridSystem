"""模块级便捷函数 — 提供最常用的任务提交入口。

用法:
    from apps.core.tasking import submit_task

    task_id = submit_task("apps.automation.tasks.execute_scraper_task", task.id, task_name=f"scraper_{task.id}")
"""

from __future__ import annotations

from typing import Any

from .context import TaskContext
from .submission import TaskSubmissionService

# 模块级单例
_submission_service: TaskSubmissionService | None = None


def _get_submission_service() -> TaskSubmissionService:
    global _submission_service
    if _submission_service is None:
        _submission_service = TaskSubmissionService()
    return _submission_service


def submit_task(
    target: str,
    *pos_args: Any,
    task_name: str | None = None,
    timeout: Any | None = None,
    group: str | None = None,
    hook: Any | None = None,
    context: TaskContext | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """提交异步任务（最常用入口）。

    等价于 ``TaskSubmissionService().submit(...)``，但不需要实例化。

    Args:
        target: 任务函数的 dotted path（如 "apps.automation.tasks.execute_scraper_task"）
        *pos_args: 位置参数（直接传给任务函数）
        task_name: 任务名称（用于日志追踪和 Sentry tag）
        timeout: 超时时间（秒）
        group: 任务分组
        hook: 完成钩子函数的 dotted path
        context: 任务上下文（自动注入 request_id 等）
        kwargs: 关键字参数（传给任务函数）

    Returns:
        任务 ID 字符串
    """
    service = _get_submission_service()
    return service.submit(
        target,
        args=list(pos_args) if pos_args else None,
        kwargs=kwargs,
        task_name=task_name,
        timeout=timeout,
        group=group,
        hook=hook,
        context=context,
    )


__all__ = ["TaskSubmissionService", "submit_task"]
