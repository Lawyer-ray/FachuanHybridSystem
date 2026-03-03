from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class JurisdictionAnalysis(models.Model):
    id: int
    assessment = models.OneToOneField(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="jurisdiction_analysis",
        verbose_name=_("关联评估记录"),
    )
    has_agreed_jurisdiction = models.BooleanField(default=False, verbose_name=_("是否有约定管辖"))
    agreed_court = models.CharField(max_length=255, blank=True, default="", verbose_name=_("约定管辖法院"))
    is_agreed_valid = models.BooleanField(blank=True, null=True, verbose_name=_("约定管辖是否有效"))
    invalid_reason = models.CharField(max_length=255, blank=True, default="", verbose_name=_("约定无效原因"))
    plaintiff_location = models.CharField(max_length=255, verbose_name=_("原告所在地"))
    defendant_location = models.CharField(max_length=255, verbose_name=_("被告住所地"))
    recommended_court = models.CharField(max_length=255, verbose_name=_("推荐管辖法院"))
    recommendation_reason = models.TextField(verbose_name=_("推荐理由"))
    alternative_court = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备选管辖法院"))
    legal_basis = models.TextField(verbose_name=_("法律依据"))

    class Meta:
        verbose_name = _("管辖权分析")
        verbose_name_plural = _("管辖权分析")

    def __str__(self) -> str:
        return f"管辖权: {self.recommended_court}"
