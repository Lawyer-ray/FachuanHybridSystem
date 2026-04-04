"""
自动化模块信号处理

处理模型保存、删除等事件，自动触发相关操作。
"""

import logging
from pathlib import Path
from typing import Any

from django.db.models import Model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_q.tasks import async_task

from .models import CourtSMS, CourtSMSStatus, PreservationQuote, QuoteStatus, ScraperTask, ScraperTaskStatus

logger = logging.getLogger("apps.automation")


@receiver(post_save, sender=PreservationQuote)
def auto_submit_preservation_quote(
    sender: type[Model], instance: PreservationQuote, created: bool, **kwargs: Any
) -> None:
    """
    自动提交询价任务到 Django Q 队列

    当创建新的询价任务时，自动提交到 Django Q 异步队列执行。
    """
    if not created:
        return

    if instance.status != QuoteStatus.PENDING:
        return

    try:
        task_id = async_task(
            "apps.automation.tasks.execute_preservation_quote_task",
            instance.id,
            task_name=f"询价任务 #{instance.id}",
            timeout=600,
        )

        logger.info(
            "✅ 询价任务 #%s 已自动提交到队列，Task ID: %s",
            instance.id,
            task_id,
            extra={"action": "auto_submit_quote", "quote_id": instance.id, "task_id": task_id},
        )

    except Exception as e:
        logger.error(
            "❌ 自动提交询价任务 #%s 失败: %s",
            instance.id,
            e,
            extra={"action": "auto_submit_quote_failed", "quote_id": instance.id, "error": str(e)},
            exc_info=True,
        )


def _handle_sms_download_success(sms: Any, instance: Any) -> None:
    """处理下载成功的 SMS"""
    if sms.status == CourtSMSStatus.DOWNLOADING:
        sms.status = CourtSMSStatus.MATCHING
        sms.save()
        logger.info("✅ 下载任务完成，进入匹配阶段: SMS ID=%s, Task ID=%s", sms.id, instance.id)
    elif sms.status == CourtSMSStatus.MATCHING:
        logger.info("✅ 下载任务完成，继续匹配流程: SMS ID=%s, Task ID=%s", sms.id, instance.id)

    task_id = async_task(
        "apps.automation.services.sms.court_sms_service.process_sms_async",
        sms.id,
        task_name=f"court_sms_continue_{sms.id}",
    )
    logger.info("提交后续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)


def _handle_sms_download_failed(sms: Any, instance: Any) -> bool:
    """处理下载失败的 SMS，返回是否需要 continue（跳过重试逻辑）"""
    if sms.status == CourtSMSStatus.MATCHING:
        logger.info("下载失败但继续匹配流程: SMS ID=%s", sms.id)
        task_id = async_task(
            "apps.automation.services.sms.court_sms_service.process_sms_async",
            sms.id,
            task_name=f"court_sms_continue_after_download_failed_{sms.id}",
        )
        logger.info("下载失败后继续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)
        return True

    sms.status = CourtSMSStatus.DOWNLOAD_FAILED
    sms.error_message = instance.error_message or "下载任务失败"
    sms.save()
    logger.warning(
        "⚠️ 下载任务失败: SMS ID=%s, Task ID=%s, 错误: %s",
        sms.id,
        instance.id,
        instance.error_message,
    )

    if sms.retry_count < 3:
        from datetime import timedelta

        from django.utils import timezone
        from django_q.models import Schedule

        next_run = timezone.now() + timedelta(seconds=60)
        Schedule.objects.create(
            func="apps.automation.services.sms.court_sms_service.retry_download_task",
            args=str(sms.id),
            name=f"court_sms_retry_download_{sms.id}",
            schedule_type=Schedule.ONCE,
            next_run=next_run,
        )
        logger.info("提交重试下载任务: SMS ID=%s, 计划执行时间=%s", sms.id, next_run)
    else:
        sms.status = CourtSMSStatus.FAILED
        sms.error_message = f"下载失败，已重试{sms.retry_count}次"
        sms.save()
        logger.error("下载重试次数用完，标记为失败: SMS ID=%s", sms.id)
    return False


@receiver(post_save, sender=ScraperTask)
def handle_scraper_task_status_change(sender: type[Model], instance: ScraperTask, created: bool, **kwargs: Any) -> None:
    """处理 ScraperTask 状态变更，触发法院短信后续处理流程"""
    if created:
        return
    if instance.status not in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
        return

    try:
        court_sms_records = CourtSMS.objects.filter(scraper_task=instance)
        for sms in court_sms_records:
            if sms.status not in [CourtSMSStatus.DOWNLOADING, CourtSMSStatus.MATCHING]:
                continue
            if instance.status == ScraperTaskStatus.SUCCESS:
                _handle_sms_download_success(sms, instance)
            elif instance.status == ScraperTaskStatus.FAILED:
                if _handle_sms_download_failed(sms, instance):
                    continue
    except Exception as e:
        logger.error(
            "❌ 处理下载完成信号失败: Task ID=%s, 错误: %s",
            instance.id,
            e,
            extra={"action": "download_signal_failed", "task_id": instance.id, "error": str(e)},
            exc_info=True,
        )


@receiver(post_delete, dispatch_uid="cleanup_court_document_local_file")
def cleanup_court_document_local_file(sender: type, **kwargs: Any) -> None:
    """
    删除 CourtDocument 记录时，自动清理下载的法院文书物理文件

    CourtDocument 使用 CharField(local_file_path) 存储文件路径（非 FileField），
    因此需要通过信号手动删除物理文件。
    """
    from .models.court_document import CourtDocument

    if sender is not CourtDocument:
        return
    instance = kwargs["instance"]
    if not instance.local_file_path:
        return
    from django.conf import settings

    file_path = Path(instance.local_file_path)
    if not file_path.is_absolute():
        file_path = Path(settings.MEDIA_ROOT) / instance.local_file_path
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(
                "已清理法院文书物理文件",
                extra={"file_path": str(file_path), "court_sms_id": instance.court_sms_id},
            )
        except OSError as exc:
            logger.error(
                "清理法院文书物理文件失败",
                extra={"file_path": str(file_path), "error": str(exc)},
            )


@receiver(post_delete, dispatch_uid="cleanup_gsxt_report_task_file")
def cleanup_gsxt_report_task_file(sender: type, **kwargs: Any) -> None:
    """GsxtReportTask 使用 FileField(report_file) 存储企业信用报告 PDF"""
    from .models.gsxt_report import GsxtReportTask

    if sender is not GsxtReportTask:
        return
    instance = kwargs["instance"]
    if instance.report_file:
        try:
            instance.report_file.delete(save=False)
            logger.info("已清理企业信用报告文件", extra={"file_path": str(instance.report_file)})
        except Exception:
            logger.exception("清理企业信用报告失败")
