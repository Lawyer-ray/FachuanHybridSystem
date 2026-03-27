"""
Automation tasks package entrypoints.

This module intentionally re-exports legacy task callables so string-based
imports (for example Django Q: ``apps.automation.tasks.execute_scraper_task``)
keep working while ``apps/automation/tasks`` exists as a package.
"""

from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any


@lru_cache(maxsize=1)
def _load_legacy_tasks_module() -> ModuleType:
    legacy_tasks_path = Path(__file__).resolve().parent.parent / "tasks.py"
    spec = spec_from_file_location("apps.automation._legacy_tasks", legacy_tasks_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy automation tasks module: {legacy_tasks_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_stuck_tasks() -> None:
    _load_legacy_tasks_module().check_stuck_tasks()


def execute_scraper_task(task_id: int, **kwargs: Any) -> None:
    _load_legacy_tasks_module().execute_scraper_task(task_id, **kwargs)


def process_pending_tasks() -> int:
    return _load_legacy_tasks_module().process_pending_tasks()


def reset_running_tasks() -> int:
    return _load_legacy_tasks_module().reset_running_tasks()


def startup_check() -> dict[str, int]:
    return _load_legacy_tasks_module().startup_check()


def execute_preservation_quote_task(quote_id: int) -> dict[str, Any]:
    return _load_legacy_tasks_module().execute_preservation_quote_task(quote_id)


__all__ = [
    "check_stuck_tasks",
    "execute_scraper_task",
    "process_pending_tasks",
    "reset_running_tasks",
    "startup_check",
    "execute_preservation_quote_task",
]
