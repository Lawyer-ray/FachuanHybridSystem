"""
自动化模块信号处理

处理模型删除事件，自动触发文件清理。
创建和更新事件已迁移至 django-lifecycle @hook 装饰器。
"""

import logging
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.automation")


@receiver(post_delete, dispatch_uid="cleanup_court_document_local_file")
def cleanup_court_document_local_file(sender: type, **kwargs: Any) -> None:  # pragma: no cover
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

    from apps.core.services.storage_service import resolve_media_path

    file_path = resolve_media_path(instance.local_file_path)
    if file_path.exists():
        try:
            transaction.on_commit(lambda p=file_path: _unlink_court_doc(p, instance.scraper_task_id))  # type: ignore[misc]  # mypy 对带默认参 lambda 的推断限制
        except OSError as exc:
            logger.error(
                "清理法院文书物理文件失败",
                extra={"file_path": str(file_path), "error": str(exc)},
            )


def _unlink_court_doc(file_path: Path, scraper_task_id: Any) -> None:
    try:
        file_path.unlink()
        logger.info(
            "已清理法院文书物理文件",
            extra={"file_path": str(file_path), "scraper_task_id": scraper_task_id},
        )
    except OSError as exc:
        logger.error(
            "清理法院文书物理文件失败",
            extra={"file_path": str(file_path), "error": str(exc)},
        )


@receiver(post_delete, dispatch_uid="cleanup_gsxt_report_task_file")
def cleanup_gsxt_report_task_file(sender: type, **kwargs: Any) -> None:  # pragma: no cover
    """GsxtReportTask 使用 FileField(report_file) 存储企业信用报告 PDF"""
    from .models.gsxt_report import GsxtReportTask

    if sender is not GsxtReportTask:
        return
    instance = kwargs["instance"]
    if instance.report_file:
        try:
            transaction.on_commit(lambda f=instance.report_file: f.delete(save=False))  # type: ignore[misc]  # mypy 对带默认参 lambda 的推断限制
            logger.info("已清理企业信用报告文件", extra={"file_path": str(instance.report_file)})
        except Exception:
            logger.exception("清理企业信用报告失败")


@receiver(post_delete, dispatch_uid="cleanup_court_sms_intake_materials")
def cleanup_court_sms_intake_materials(sender: type, **kwargs: Any) -> None:  # pragma: no cover
    """删除 CourtSMS 时清理「客户转交材料」落盘的文件。

    法院短信通道的下载原件挂在 ScraperTask / CourtDocument 上，由
    ``cleanup_court_document_local_file`` 负责；客户转交通道没有下载任务，
    文件只由 CourtSMS.document_file_paths 引用，不在这里清理就会成为孤儿。
    已重命名归档到案件文件夹/案件日志的副本是独立拷贝，不受影响。
    """
    from .models.court_sms import CourtSMS

    if sender is not CourtSMS:
        return
    instance = kwargs["instance"]
    paths = instance.document_file_paths
    if not isinstance(paths, list) or not paths:
        return

    from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService
    from apps.core.services.storage_service import delete_media_file

    intake = CourtSMSDocumentIntakeService()
    # 只删本通道目录下的文件：下载原件由 ScraperTask 信号管，两边不越权
    doomed = [p for p in paths if isinstance(p, str) and intake._is_intake_path(p)]
    if not doomed:
        return

    def _unlink_all() -> None:
        removed = sum(1 for p in doomed if delete_media_file(p))
        logger.info(
            "已清理客户转交材料物理文件",
            extra={"sms_id": instance.id, "requested": len(doomed), "removed": removed},
        )

    transaction.on_commit(_unlink_all)
