"""
Automation tasks package.

Re-exports all task callables so string-based imports
(for example Django Q: ``apps.automation.tasks.execute_scraper_task``)
keep working.
"""

from .scraping_tasks import (
    execute_preservation_quote_task,
    execute_scraper_task,
    process_pending_tasks,
    reset_running_tasks,
)

__all__ = [
    "execute_preservation_quote_task",
    "execute_scraper_task",
    "process_pending_tasks",
    "reset_running_tasks",
]
