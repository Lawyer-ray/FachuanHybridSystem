from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class StrategyType(models.TextChoices):
    PAYMENT_ORDER = "payment_order", _("支付令")
    SMALL_CLAIMS = "small_claims", _("小额诉讼")
    SUMMARY_PROCEDURE = "summary_procedure", _("简易程序")
    ORDINARY_PROCEDURE = "ordinary_procedure", _("普通程序")
    PRE_LITIGATION_MEDIATION = "pre_litigation_mediation", _("诉前调解")


class LitigationStrategy(models.Model):
    id: int
    assessment = models.OneToOneField(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="litigation_strategy",
        verbose_name=_("关联评估记录"),
    )
    strategy_type = models.CharField(
        max_length=32,
        choices=StrategyType.choices,
        verbose_name=_("推荐策略类型"),
    )
    recommendation_reason = models.TextField(verbose_name=_("推荐理由"))
    estimated_duration = models.CharField(
        max_length=64, verbose_name=_("预计周期")
    )
    applicable_conditions = models.TextField(verbose_name=_("适用条件说明"))
    suggest_preservation = models.BooleanField(
        default=False, verbose_name=_("是否建议财产保全")
    )
    preservation_reason = models.TextField(
        blank=True, default="", verbose_name=_("保全建议理由")
    )

    class Meta:
        verbose_name = _("起诉策略推荐")
        verbose_name_plural = _("起诉策略推荐")

    def __str__(self) -> str:
        return f"策略: {self.get_strategy_type_display()}"
