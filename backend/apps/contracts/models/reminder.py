"""Module for reminder."""

from __future__ import annotations

from datetime import date, datetime

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract


class ContractReminderType(models.TextChoices):
    HEARING = "hearing", _("开庭")
    ASSET_PRESERVATION = "asset_preservation", _("财产保全")
    EVIDENCE_DEADLINE = "evidence_deadline", _("举证期限")
    STATUTE_LIMITATIONS = "statute_limitations", _("时效")
    APPEAL_PERIOD = "appeal_period", _("上诉期")
    OTHER = "other", _("其他")


class ContractReminder(models.Model):
    id: int
    contract_id: int
    contract: Contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="contract_reminders",
        related_query_name="contract_reminder",
        verbose_name=_("合同"),
    )
    kind: str = models.CharField(max_length=32, choices=ContractReminderType.choices, verbose_name=_("类型"))
    content: str = models.CharField(max_length=255, verbose_name=_("提醒事项"))
    due_date: date = models.DateField(verbose_name=_("到期日期"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("重要日期提醒")
        verbose_name_plural = _("重要日期提醒")

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.kind}-{self.due_date}"
