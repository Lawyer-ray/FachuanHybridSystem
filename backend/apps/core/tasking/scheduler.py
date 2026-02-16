"""Module for scheduler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast


class TaskScheduler(Protocol):
    def schedule_interval(
        self,
        *,
        func: str,
        minutes: int,
        name: str,
        args: Sequence[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        repeats: int = -1,
    ) -> str: ...

    def delete_schedules(self, *, name: str | None = None, func: str | None = None) -> int: ...


@dataclass(frozen=True)
class DjangoQTaskScheduler:
    def schedule_interval(
        self,
        *,
        func: str,
        minutes: int,
        name: str,
        args: Sequence[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        repeats: int = -1,
    ) -> str:
        from django_q.tasks import schedule

        return cast(
            str,
            schedule(
                func,
                *(list(args or [])),
                **(kwargs or {}),
                schedule_type="I",
                minutes=minutes,
                name=name,
                repeats=repeats,
            ),
        )

    def delete_schedules(self, *, name: str | None = None, func: str | None = None) -> int:
        from django_q.models import Schedule

        qs = Schedule.objects.all()
        if name is not None:
            qs = qs.filter(name=name)
        if func is not None:
            qs = qs.filter(func=func)
        count = cast(int, qs.count())
        qs.delete()
        return count
