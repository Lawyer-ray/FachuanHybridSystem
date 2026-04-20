"""
自动化模块信号处理

处理模型删除事件，自动触发文件清理。
创建和更新事件已迁移至 django-lifecycle @hook 装饰器。
"""

import logging
from pathlib import Path
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.automation")


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
