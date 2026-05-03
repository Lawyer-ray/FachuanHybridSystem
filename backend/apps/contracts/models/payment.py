"""Module for payment."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from .contract import Contract


class InvoiceStatus(models.TextChoices):
    UNINVOICED = "UNINVOICED", _("未开票")
    INVOICED_PARTIAL = "INVOICED_PARTIAL", _("部分开票")
    INVOICED_FULL = "INVOICED_FULL", _("已开票")


class ContractPayment(models.Model):
    id: int
    contract_id: int
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="payments", verbose_name=_("合同"))
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("收款金额"))
    received_at = models.DateField(default=timezone.localdate, verbose_name=_("收款日期"))
    invoice_status = models.CharField(
        max_length=32, choices=InvoiceStatus.choices, default=InvoiceStatus.UNINVOICED, verbose_name=_("开票状态")
    )
    invoiced_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("已开票金额"))
    note = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("合同收款")
        verbose_name_plural = _("合同收款")
        indexes: ClassVar = [
            models.Index(fields=["contract", "received_at"]),
            models.Index(fields=["invoice_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract.name} - ¥{self.amount}"
