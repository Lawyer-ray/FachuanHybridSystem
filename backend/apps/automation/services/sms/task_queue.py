"""Business logic services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class TaskQueue(Protocol):
    def enqueue(
        self, func_path: str | Callable[..., Any], *args: Any, task_name: str | None = None, **kwargs: Any
    ) -> str: ...


@dataclass(frozen=True)
class DjangoQTaskQueue:
    def enqueue(
        self, func_path: str | Callable[..., Any], *args: Any, task_name: str | None = None, **kwargs: Any
    ) -> Any:
        from apps.core.tasking import submit_task

        target = f"{func_path.__module__}.{func_path.__qualname__}" if callable(func_path) else func_path
        return submit_task(target, *args, task_name=task_name)
