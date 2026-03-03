from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class LPRRate(models.Model):
    id: int
    effective_date = models.DateField(unique=True, verbose_name=_("生效日期"))
    rate_1y = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("一年期LPR(%)"))
    rate_5y = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("五年期LPR(%)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        ordering: ClassVar = ["-effective_date"]
        verbose_name = _("LPR利率")
        verbose_name_plural = _("LPR利率")

    def __str__(self) -> str:
        return f"LPR {self.effective_date} - 1Y:{self.rate_1y}% 5Y:{self.rate_5y}%"
