"""Database models."""

from datetime import datetime
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


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
    contract_id: int | None
    case_id: int | None
    case_log_id: int | None
    contract: Any = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
        verbose_name=_("合同"),
    )
    case: Any = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
        verbose_name=_("案件"),
    )
    case_log: Any = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
        verbose_name=_("案件日志"),
    )
    reminder_type: Any = models.CharField(max_length=64, choices=ReminderType.choices, verbose_name=_("类型"))
    content: Any = models.CharField(max_length=255, verbose_name=_("提醒事项"))
    due_at: Any = models.DateTimeField(verbose_name=_("到期时间"))
    metadata: Any = models.JSONField(default=dict, blank=True, verbose_name=_("扩展数据"))
    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: Any = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("重要日期提醒")
        verbose_name_plural = _("重要日期提醒")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=(Q(contract__isnull=True) | Q(case__isnull=True))
                & (Q(contract__isnull=True) | Q(case_log__isnull=True))
                & (Q(case__isnull=True) | Q(case_log__isnull=True)),
                name="reminders_reminder_bind_at_most_one",
            )
        ]
        indexes: ClassVar = [
            models.Index(fields=["due_at"]),
            models.Index(fields=["reminder_type"]),
        ]

    def clean(self) -> None:
        super().clean()
        bound_count = sum(target_id is not None for target_id in (self.contract_id, self.case_id, self.case_log_id))
        if bound_count > 1:
            raise ValidationError(_("合同、案件、案件日志最多只能绑定一个"))

    def __str__(self) -> str:
        if self.contract_id is not None:
            target = f"contract:{self.contract_id}"
        elif self.case_id is not None:
            target = f"case:{self.case_id}"
        elif self.case_log_id is not None:
            target = f"case_log:{self.case_log_id}"
        else:
            target = "unbound"
        return f"{target}-{self.reminder_type}-{self.due_at}"
