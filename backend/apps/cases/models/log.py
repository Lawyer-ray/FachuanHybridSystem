"""Module for log."""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cases.utils import validate_case_log_attachment
from apps.core.storage import KeepOriginalNameStorage

from .case import Case

# 案件日志附件存储
case_log_storage = KeepOriginalNameStorage()


def validate_log_attachment(file) -> None:
    """验证日志附件"""
    name = getattr(file, "name", "")
    size = getattr(file, "size", 0)
    ok, error = validate_case_log_attachment(name, size)
    if not ok:
        from django.core.exceptions import ValidationError

        raise ValidationError(_(error or "附件校验失败"))


class CaseLog(models.Model):
    id: int
    case_id: int  # 外键ID字段
    case_id: int  # 外键ID字段
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="logs", verbose_name=_("案件"))
    id: int
    content = models.TextField(verbose_name=_("日志内容"))
    actor = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="case_logs", verbose_name=_("操作人")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建日期"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("修改日期"))

    class Meta:
        verbose_name = _("案件日志")
        verbose_name_plural = _("案件日志")
        indexes: ClassVar = [
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self) -> None:
        return f"{self.case_id}-{self.actor_id}-{self.created_at}"

    @property
    def reminder_type(self) -> None:
        reminder = self.reminders.order_by("-due_at").first()
        return getattr(reminder, "reminder_type", None) if reminder else None

    @property
    def reminder_time(self) -> None:
        reminder = self.reminders.order_by("-due_at").first()
        return getattr(reminder, "due_at", None) if reminder else None


class CaseLogAttachment(models.Model):
    id: int
    log_id: int  # 外键ID字段
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="attachments", verbose_name=_("日志"))
    id: int
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
    log_id: int  # 外键ID字段
    actor_id: int  # 外键ID字段
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="versions", verbose_name=_("日志"))
    id: int
    content = models.TextField(verbose_name=_("历史内容"))
    version_at = models.DateTimeField(auto_now_add=True, verbose_name=_("版本时间"))
    actor = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="case_log_versions", verbose_name=_("操作者")
    )

    class Meta:
        verbose_name = _("案件日志版本")
        verbose_name_plural = _("案件日志版本")

    def __str__(self) -> None:
        return f"{self.log_id}-{self.version_at}"
