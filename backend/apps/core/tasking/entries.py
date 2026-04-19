"""Module for entries."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any, cast

from .context import TaskContext, set_current_request_id

logger = logging.getLogger("apps.core.tasking")


def _import_callable(dotted_path: str) -> Callable[..., Any]:
    module_path, attr = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return cast(Callable[..., Any], getattr(module, attr))


def run_task(
    target: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> Any:
    task_ctx = TaskContext.from_dict(context)
    request_id = task_ctx.request_id or task_ctx.correlation_id
    set_current_request_id(request_id)

    # 设置 task_name 到 ContextVar，供日志和 Sentry 追踪
    if task_ctx.task_name:
        from apps.core.infrastructure.request_context import set_request_context

        set_request_context(task_name=task_ctx.task_name)

    fn = _import_callable(target)
    try:
        return fn(*(args or []), **(kwargs or {}))
    except Exception as e:
        logger.error(
            "task_failed",
            extra={
                "target": target,
                "task_name": task_ctx.task_name,
                "entity_id": task_ctx.entity_id,
                "correlation_id": task_ctx.correlation_id,
                "error": str(e),
                **(task_ctx.extra or {}),
            },
            exc_info=True,
        )
        raise
