from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentRecord(models.Model):
    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="dispute_payments",
        verbose_name=_("关联案件"),
    )
    payment_date = models.DateField(verbose_name=_("还款日期"))
    payment_amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name=_("还款金额"))
    offset_fee = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵费用"))
    offset_interest = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵利息"))
    offset_principal = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵本金"))
    remaining_principal = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name=_("剩余本金"))
    remarks = models.TextField(blank=True, default="", verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        ordering: ClassVar = ["payment_date"]
        verbose_name = _("还款冲抵记录")
        verbose_name_plural = _("还款冲抵记录")

    def __str__(self) -> str:
        return f"{self.payment_date} - {self.payment_amount}"
