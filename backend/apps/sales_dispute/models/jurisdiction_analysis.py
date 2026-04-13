from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class JurisdictionAnalysis(models.Model):
    id: int
    assessment_id: int
    assessment: models.OneToOneField[models.Model, models.Model] = models.OneToOneField(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="jurisdiction_analysis",
        verbose_name=_("关联评估记录"),
    )
    has_agreed_jurisdiction: bool = models.BooleanField(default=False, verbose_name=_("是否有约定管辖"))  # type: ignore[assignment]
    agreed_court: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("约定管辖法院"))  # type: ignore[assignment]
    is_agreed_valid: bool | None = models.BooleanField(blank=True, null=True, verbose_name=_("约定管辖是否有效"))  # type: ignore[assignment]
    invalid_reason: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("约定无效原因"))  # type: ignore[assignment]
    plaintiff_location: str = models.CharField(max_length=255, verbose_name=_("原告所在地"))  # type: ignore[assignment]
    defendant_location: str = models.CharField(max_length=255, verbose_name=_("被告住所地"))  # type: ignore[assignment]
    recommended_court: str = models.CharField(max_length=255, verbose_name=_("推荐管辖法院"))  # type: ignore[assignment]
    recommendation_reason: str = models.TextField(verbose_name=_("推荐理由"))  # type: ignore[assignment]
    alternative_court: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备选管辖法院"))  # type: ignore[assignment]
    legal_basis: str = models.TextField(verbose_name=_("法律依据"))  # type: ignore[assignment]

    class Meta:
        verbose_name = _("管辖权分析")
        verbose_name_plural = _("管辖权分析")

    def __str__(self) -> str:
        return f"管辖权: {self.recommended_court}"
