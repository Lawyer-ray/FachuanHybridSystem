"""Module for scraper task handler."""

import logging
from typing import Any

from django_q.models import Schedule

from apps.automation.models import ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.automation.tasking.retry_policy import ExponentialBackoffRetryPolicy

logger = logging.getLogger("apps.automation")


class ScraperTaskHandler:
    def __init__(self, *, retry_policy: ExponentialBackoffRetryPolicy | None = None) -> None:
        self.retry_policy = retry_policy or ExponentialBackoffRetryPolicy()

    def _get_scraper_map(self) -> dict[str, type]:
        from apps.automation.services.scraper.scrapers import CourtDocumentScraper, CourtFilingScraper

        return {
            ScraperTaskType.COURT_DOCUMENT: CourtDocumentScraper,
            ScraperTaskType.COURT_FILING: CourtFilingScraper,
        }

    def execute(self, *, task: ScraperTask) -> Any:
        scraper_map = self._get_scraper_map()
        scraper_class = scraper_map.get(task.task_type)

        if not scraper_class:
            error_msg = f"不支持的任务类型: {task.task_type}"
            logger.error(error_msg)
            task.status = ScraperTaskStatus.FAILED
            task.error_message = error_msg
            task.save(update_fields=["status", "error_message", "updated_at"])
            return None

        scraper = scraper_class(task)
        return scraper.execute()

    def schedule_retry(self, *, task: ScraperTask) -> None:
        next_run_time, delay_seconds = self.retry_policy.next_run_time(retry_count=task.retry_count)  # type: ignore[func-returns-value]
        Schedule.objects.create(
            func="apps.automation.tasks.execute_scraper_task",
            args=str(task.id),
            schedule_type=Schedule.ONCE,
            next_run=next_run_time,
            name=f"retry_task_{task.id}_{task.retry_count}",
        )
        logger.info(
            f"任务 {task.id} 将在 {delay_seconds} 秒后重试(第 {task.retry_count}/{task.max_retries} 次,指数退避)"
        )
        logger.info(f"计划执行时间: {next_run_time}")
