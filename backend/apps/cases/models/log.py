"""Module for log."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE
from apps.core.storage import KeepOriginalNameStorage

_SENTINEL = object()

from .case import Case

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

# 案件日志附件存储
case_log_storage = KeepOriginalNameStorage()
logger = logging.getLogger(__name__)


def validate_log_attachment(file: UploadedFile) -> None:
    """验证日志附件"""
    name = str(getattr(file, "name", ""))
    size: int = int(getattr(file, "size", 0) or 0)
    ext = Path(name).suffix.lower()
    if ext not in CASE_LOG_ALLOWED_EXTENSIONS:
        from django.core.exceptions import ValidationError

        raise ValidationError(_("不支持的文件类型"))
    if size and size > CASE_LOG_MAX_FILE_SIZE:
        from django.core.exceptions import ValidationError

        raise ValidationError(_("文件大小超过50MB限制"))


class CaseLog(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="logs", verbose_name=_("案件"))
    content = models.TextField(verbose_name=_("日志内容"))
    actor = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="case_logs", verbose_name=_("操作人")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建日期"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("修改日期"))

    if TYPE_CHECKING:
        attachments: RelatedManager[CaseLogAttachment]
        versions: RelatedManager[CaseLogVersion]

    class Meta:
        verbose_name = _("案件日志")
        verbose_name_plural = _("案件日志")
        indexes: ClassVar = [
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.actor_id}-{self.created_at}"

    def _exported_reminders(self) -> list[dict[str, Any]]:
        cached = getattr(self, "_cached_exported_reminders", _SENTINEL)
        if cached is not _SENTINEL:
            return cached
        if not getattr(self, "id", None):
            self._cached_exported_reminders = []
            return []

        reminders: list[dict[str, Any]]
        try:
            from apps.core.interfaces import ServiceLocator

            reminder_service = ServiceLocator.get_reminder_service()
            reminders = reminder_service.export_case_log_reminders_internal(case_log_id=int(self.id))
        except Exception:
            logger.exception("case_log_export_reminders_failed", extra={"case_log_id": int(self.id)})
            reminders = []
        self._cached_exported_reminders = reminders
        return reminders

    @property
    def reminder_entries(self) -> list[dict[str, Any]]:
        return self._exported_reminders()

    @property
    def has_reminders(self) -> bool:
        return bool(self._exported_reminders())

    @property
    def reminder_count(self) -> int:
        return len(self._exported_reminders())

    @property
    def _latest_reminder(self) -> Any | None:
        """缓存最近的提醒记录，避免重复查询。"""
        cached = getattr(self, "_cached_latest_reminder", _SENTINEL)
        if cached is not _SENTINEL:
            return cached
        if not getattr(self, "id", None):
            self._cached_latest_reminder = None
            return None

        reminder: dict[str, Any] | None = None
        try:
            from apps.core.interfaces import ServiceLocator

            reminder_service = ServiceLocator.get_reminder_service()
            reminder = reminder_service.get_latest_case_log_reminder_internal(case_log_id=int(self.id))
        except Exception:
            logger.exception("case_log_latest_reminder_failed", extra={"case_log_id": int(self.id)})
            reminders = self._exported_reminders()
            reminder = reminders[-1] if reminders else None

        self._cached_latest_reminder = reminder
        return reminder

    @property
    def reminder_type(self) -> str | None:
        """获取最近的提醒类型。"""
        reminder = self._latest_reminder
        if reminder is None:
            return None
        if isinstance(reminder, dict):
            return str(reminder.get("reminder_type") or "")
        return str(getattr(reminder, "reminder_type", ""))

    @property
    def reminder_time(self) -> datetime | None:
        """获取最近的提醒时间。"""
        reminder = self._latest_reminder
        if reminder is None:
            return None
        due_at = reminder.get("due_at") if isinstance(reminder, dict) else getattr(reminder, "due_at", None)
        return due_at if isinstance(due_at, datetime) else None


class CaseLogAttachment(models.Model):
    id: int
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="attachments", verbose_name=_("日志"))
    file = models.FileField(
        upload_to="case_logs/",
        storage=case_log_storage,
        validators=[validate_log_attachment],
        verbose_name=_("相关文书"),
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))

    class Meta:
        verbose_name = _("案件日志附件")
        verbose_name_plural = _("案件日志附件")


class CaseLogVersion(models.Model):
    id: int
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="versions", verbose_name=_("日志"))
    content = models.TextField(verbose_name=_("历史内容"))
    version_at = models.DateTimeField(auto_now_add=True, verbose_name=_("版本时间"))
    actor = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="case_log_versions", verbose_name=_("操作者")
    )

    class Meta:
        verbose_name = _("案件日志版本")
        verbose_name_plural = _("案件日志版本")

    def __str__(self) -> str:
        return f"{self.log_id}-{self.version_at}"
