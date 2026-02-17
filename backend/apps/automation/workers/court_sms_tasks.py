"""Module for court sms tasks."""

from __future__ import annotations

from typing import Any, cast

from apps.core.interfaces import ServiceLocator


def process_sms(sms_id: int) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

    return cast(
        None, ProcessSmsUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)
    )


def process_sms_from_matching(sms_id: int) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromMatchingUsecase

    return cast(
        None,
        ProcessSmsFromMatchingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id),
    )


def process_sms_from_renaming(sms_id: int) -> None:
    from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromRenamingUsecase

    return cast(
        None,
        ProcessSmsFromRenamingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id),
    )


def retry_download_task(sms_id: Any, **kwargs: Any) -> None:
    from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

    sms_id = int(sms_id)
    return cast(
        None, RetryDownloadUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)
    )
