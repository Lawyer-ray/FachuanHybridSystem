"""Module for task runner."""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("apps.automation")


class TaskRunner:
    def __init__(self, *, on_error: Callable[[Exception], None] | None = None) -> None:
        self._on_error = on_error

    def run(self, *, fn: Callable[[], Any], task_name: str, extra: dict[str, Any] | None = None) -> Any:
        try:
            return fn()
        except Exception as e:
            logger.error(f"{task_name} 执行异常: {e}", exc_info=True, extra=extra or {})
            if self._on_error:
                self._on_error(e)
            raise
