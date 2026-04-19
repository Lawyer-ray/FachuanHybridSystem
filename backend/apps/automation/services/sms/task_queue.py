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

        return submit_task(func_path, *args, task_name=task_name)
