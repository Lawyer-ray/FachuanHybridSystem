from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class LPRRate(models.Model):
    id: int
    effective_date: date = models.DateField(unique=True, verbose_name=_("生效日期"))  # type: ignore[assignment]
    rate_1y: Decimal = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("一年期LPR(%)"))  # type: ignore[assignment]
    rate_5y: Decimal = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("五年期LPR(%)"))  # type: ignore[assignment]
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))  # type: ignore[assignment]
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))  # type: ignore[assignment]

    class Meta:
        ordering: ClassVar = ["-effective_date"]
        verbose_name = _("LPR利率")
        verbose_name_plural = _("LPR利率")

    def __str__(self) -> str:
        return f"LPR {self.effective_date} - 1Y:{self.rate_1y}% 5Y:{self.rate_5y}%"
