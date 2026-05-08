from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentRecord(models.Model):
    id: int
    case_id: int
    case: models.ForeignKey[models.Model, models.Model] = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="dispute_payments",
        verbose_name=_("关联案件"),
    )
    payment_date: date = models.DateField(verbose_name=_("还款日期"))  # type: ignore[assignment]
    payment_amount: Decimal = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("还款金额"))  # type: ignore[assignment]
    offset_fee: Decimal = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵费用"))  # type: ignore[assignment]
    offset_interest: Decimal = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵利息"))  # type: ignore[assignment]
    offset_principal: Decimal = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("冲抵本金"))  # type: ignore[assignment]
    remaining_principal: Decimal = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("剩余本金"))  # type: ignore[assignment]
    remarks: str = models.TextField(blank=True, default="", verbose_name=_("备注"))  # type: ignore[assignment]
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))  # type: ignore[assignment]

    class Meta:
        ordering: ClassVar = ["payment_date"]
        verbose_name = _("还款冲抵记录")
        verbose_name_plural = _("还款冲抵记录")

    def __str__(self) -> str:
        return f"{self.payment_date} - {self.payment_amount}"
