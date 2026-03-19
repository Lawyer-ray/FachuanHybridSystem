from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class LPRRate(models.Model):
    """LPR利率数据模型.

    存储中国人民银行公布的贷款市场报价利率(LPR)数据。
    每月20日(遇节假日顺延)由央行公布。

    Attributes:
        effective_date: 利率生效日期
        rate_1y: 一年期LPR利率(%)
        rate_5y: 五年期以上LPR利率(%)
        source: 数据来源说明
        is_auto_synced: 是否通过自动同步获取
        created_at: 创建时间
        updated_at: 更新时间
    """

    id: int
    effective_date = models.DateField(
        unique=True, verbose_name=_("生效日期"), help_text=_("LPR利率生效日期，通常为每月20日")
    )
    rate_1y = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name=_("一年期LPR(%)"), help_text=_("一年期贷款市场报价利率")
    )
    rate_5y = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name=_("五年期LPR(%)"), help_text=_("五年期以上贷款市场报价利率")
    )
    source = models.CharField(
        max_length=255, blank=True, verbose_name=_("数据来源"), help_text=_("数据来源说明，如：中国人民银行官网")
    )
    is_auto_synced = models.BooleanField(
        default=False, verbose_name=_("自动同步"), help_text=_("是否通过系统自动同步获取")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        """Model meta options."""

        ordering: ClassVar = ["-effective_date"]
        verbose_name = _("LPR利率")
        verbose_name_plural = _("LPR利率")
        indexes = [
            models.Index(fields=["effective_date"], name="%(app_label)s_lpr_eff_date_idx"),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"LPR {self.effective_date} - 1Y:{self.rate_1y}% 5Y:{self.rate_5y}%"

    @property
    def rate_1y_decimal(self) -> Decimal:
        """Return 1-year rate as decimal (e.g., 3.45 -> 0.0345)."""
        return self.rate_1y / Decimal("100")

    @property
    def rate_5y_decimal(self) -> Decimal:
        """Return 5-year rate as decimal (e.g., 3.95 -> 0.0395)."""
        return self.rate_5y / Decimal("100")
