"""Database models."""

from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class ReminderType(models.TextChoices):
    HEARING = ("hearing", _("开庭"))
    ASSET_PRESERVATION_EXPIRES = ("asset_preservation_expires", _("财产保全到期日"))
    EVIDENCE_DEADLINE = ("evidence_deadline", _("举证到期日"))
    APPEAL_DEADLINE = ("appeal_deadline", _("上诉期到期日"))
    STATUTE_LIMITATIONS = ("statute_limitations", _("诉讼时效到期日"))
    PAYMENT_DEADLINE = ("payment_deadline", _("缴费期限"))
    SUBMISSION_DEADLINE = ("submission_deadline", _("补正/材料提交期限"))
    OTHER = ("other", _("其他"))


class Reminder(models.Model):
    id: int
    contract_id: int | None  # ForeignKey ID 字段，可为 null
    case_log_id: int | None  # ForeignKey ID 字段，可为 null
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
        verbose_name=_("合同"),
    )
    case_log = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
        verbose_name=_("案件日志"),
    )
    reminder_type = models.CharField(max_length=64, choices=ReminderType.choices, verbose_name=_("类型"))
    content = models.CharField(max_length=255, verbose_name=_("提醒事项"))
    due_at = models.DateTimeField(verbose_name=_("到期时间"))
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("扩展数据"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("重要日期提醒")
        verbose_name_plural = _("重要日期提醒")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=(Q(contract__isnull=False) & Q(case_log__isnull=True))
                | (Q(contract__isnull=True) & Q(case_log__isnull=False)),
                name="reminders_reminder_bind_exactly_one",
            )
        ]
        indexes: ClassVar = [
            models.Index(fields=["due_at"]),
            models.Index(fields=["reminder_type"]),
            models.Index(fields=["contract"]),
            models.Index(fields=["case_log"]),
        ]

    def clean(self) -> None:
        super().clean()
        if (self.contract_id is not None) == (self.case_log_id is not None):
            raise ValidationError(_("必须且只能绑定合同或案件日志之一"))

    def __str__(self) -> str:
        if self.contract_id is not None:
            target = f"contract:{self.contract_id}"
        elif self.case_log_id is not None:
            target = f"case_log:{self.case_log_id}"
        else:
            target = "unbound"
        return f"{target}-{self.reminder_type}-{self.due_at}"
