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
    assessment_id: int
    assessment: models.OneToOneField[models.Model, models.Model] = models.OneToOneField(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="litigation_strategy",
        verbose_name=_("关联评估记录"),
    )
    strategy_type: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=StrategyType.choices,
        verbose_name=_("推荐策略类型"),
    )
    recommendation_reason: str = models.TextField(verbose_name=_("推荐理由"))  # type: ignore[assignment]
    estimated_duration: str = models.CharField(max_length=64, verbose_name=_("预计周期"))  # type: ignore[assignment]
    applicable_conditions: str = models.TextField(verbose_name=_("适用条件说明"))  # type: ignore[assignment]
    suggest_preservation: bool = models.BooleanField(default=False, verbose_name=_("是否建议财产保全"))  # type: ignore[assignment]
    preservation_reason: str = models.TextField(blank=True, default="", verbose_name=_("保全建议理由"))  # type: ignore[assignment]

    class Meta:
        verbose_name = _("起诉策略推荐")
        verbose_name_plural = _("起诉策略推荐")

    def __str__(self) -> str:
        strategy_labels = {
            StrategyType.PAYMENT_ORDER.value: _("支付令"),
            StrategyType.SMALL_CLAIMS.value: _("小额诉讼"),
            StrategyType.SUMMARY_PROCEDURE.value: _("简易程序"),
            StrategyType.ORDINARY_PROCEDURE.value: _("普通程序"),
            StrategyType.PRE_LITIGATION_MEDIATION.value: _("诉前调解"),
        }
        label = strategy_labels.get(self.strategy_type, self.strategy_type)
        return f"策略: {label}"
