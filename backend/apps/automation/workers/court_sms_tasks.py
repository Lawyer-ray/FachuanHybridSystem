"""Module for court sms tasks."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.core.interfaces import ServiceLocator

logger = logging.getLogger("apps.automation")


def _mark_entry_failure(entry: str, sms_id: int | str, error: BaseException) -> None:
    """任务入口级兜底：进入处理服务之前的失败（import/服务装配等）也落库为 FAILED。

    Service 层 process_sms 已自带 FAILED 落库；本兜底只补构造阶段静默死亡的缺口
    （实例：qcluster 未随代码更新重启，worker 内存残留旧模块导致 ImportError，
    短信永远卡在 pending 且 error_message 为空，admin 页面看不到任何异常）。
    已是 FAILED/COMPLETED 的记录跳过，避免覆盖 Service 层更精确的错误信息。
    """
    from apps.automation.models import CourtSMS, CourtSMSStatus

    try:
        updated = (
            CourtSMS.objects.filter(id=sms_id)
            .exclude(status__in=[CourtSMSStatus.FAILED, CourtSMSStatus.COMPLETED])
            .update(
                status=CourtSMSStatus.FAILED,
                error_message=f"任务入口异常({entry}): {error}",
                updated_at=timezone.now(),
            )
        )
    except Exception:
        logger.error("法院短信任务入口失败落库失败: entry=%s, SMS ID=%s", entry, sms_id, exc_info=True)
        return
    if updated:
        logger.error("法院短信任务入口失败已落库: entry=%s, SMS ID=%s, 错误: %s", entry, sms_id, error)


def process_sms(sms_id: int, process_options: dict[str, Any] | None = None) -> None:
    try:
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

        ProcessSmsUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(
            sms_id=sms_id,
            process_options=process_options,
        )
    except Exception as exc:
        _mark_entry_failure("process_sms", sms_id, exc)
        raise


def process_sms_from_matching(sms_id: int) -> None:
    try:
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromMatchingUsecase

        ProcessSmsFromMatchingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)
    except Exception as exc:
        _mark_entry_failure("process_sms_from_matching", sms_id, exc)
        raise


def process_sms_from_renaming(sms_id: int) -> None:
    try:
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromRenamingUsecase

        ProcessSmsFromRenamingUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=sms_id)
    except Exception as exc:
        _mark_entry_failure("process_sms_from_renaming", sms_id, exc)
        raise


def retry_download_task(sms_id: Any, **kwargs: Any) -> None:
    try:
        from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

        RetryDownloadUsecase(court_sms_service=ServiceLocator.get_court_sms_service()).execute(sms_id=int(sms_id))
    except Exception as exc:
        _mark_entry_failure("retry_download_task", sms_id, exc)
        raise


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
        logger.warning("ScraperTask %s 不存在，跳过 SMS 后续处理", task_id)
