"""Module for court sms tasks."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def process_sms(sms_id: int, process_options: dict[str, Any] | None = None) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

    ProcessSmsUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(
        sms_id=sms_id,
        process_options=process_options,
    )


def process_sms_from_matching(sms_id: int) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromMatchingUsecase

    ProcessSmsFromMatchingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)


def process_sms_from_renaming(sms_id: int) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromRenamingUsecase

    ProcessSmsFromRenamingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)


def retry_download_task(sms_id: Any, **kwargs: Any) -> None:
    from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

    sms_id = int(sms_id)
    RetryDownloadUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)


def handle_scraper_task_status_change(task_id: int) -> None:
    """Django-Q task: 处理 ScraperTask 状态变更后的 SMS 后续流程

    从 ScraperTask @hook 中延迟提交，避免在 model save 事务内执行大量 ORM I/O。
    """
    from apps.automation.models import ScraperTask
    from apps.automation.services.sms.court_sms_service import CourtSMSService

    try:
        task = ScraperTask.objects.get(id=task_id)
        CourtSMSService().handle_scraper_task_status_change(task)
    except ScraperTask.DoesNotExist:
        from django.conf import settings

        import logging

        logger = logging.getLogger("apps.automation")
        logger.warning("ScraperTask %s 不存在，跳过 SMS 后续处理", task_id)
