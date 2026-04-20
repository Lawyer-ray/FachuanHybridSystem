"""Task scheduling exceptions.

Wraps django_q exceptions behind the tasking abstraction layer so
that business code never needs to import from django_q directly.
"""

from __future__ import annotations

from django_q.exceptions import TimeoutException as TaskTimeoutError

__all__: list[str] = [
    "TaskTimeoutError",
]
