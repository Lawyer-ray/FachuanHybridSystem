from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .evidence_score import EvidenceScore
    from .jurisdiction_analysis import JurisdictionAnalysis
    from .litigation_strategy import LitigationStrategy


class ContractBasisType(models.TextChoices):
    WRITTEN = "written", _("书面合同")
    ORAL = "oral", _("口头约定")
    TRADE_CUSTOM = "trade_custom", _("交易习惯")


class LimitationStatus(models.TextChoices):
    NORMAL = "normal", _("正常")
    EXPIRING_SOON = "expiring_soon", _("即将届满")
    EXPIRED = "expired", _("已届满")


class SolvencyRating(models.TextChoices):
    GOOD = "good", _("良好")
    FAIR = "fair", _("一般")
    POOR = "poor", _("较差")
    UNKNOWN = "unknown", _("未知")


class AssessmentGrade(models.TextChoices):
    SUFFICIENT = "sufficient", _("充分")
    FAIRLY_SUFFICIENT = "fairly_sufficient", _("较充分")
    AVERAGE = "average", _("一般")
    WEAK = "weak", _("薄弱")
    SEVERELY_INSUFFICIENT = "severely_insufficient", _("严重不足")


class CaseAssessment(models.Model):
    id: int
    case = models.OneToOneField(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="sales_dispute_assessment",
        verbose_name=_("关联案件"),
    )
    contract_basis = models.CharField(
        max_length=32,
        choices=ContractBasisType.choices,
        verbose_name=_("合同基础类型"),
    )
    principal_amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name=_("债权本金")
    )
    evidence_total_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name=_("证据完整度总分")
    )
    limitation_status = models.CharField(
        max_length=32,
        choices=LimitationStatus.choices,
        default=LimitationStatus.NORMAL,
        verbose_name=_("诉讼时效状态"),
    )
    limitation_expiry_date = models.DateField(
        blank=True, null=True, verbose_name=_("时效届满日期")
    )
    solvency_rating = models.CharField(
        max_length=32,
        choices=SolvencyRating.choices,
        default=SolvencyRating.UNKNOWN,
        verbose_name=_("偿付能力评级"),
    )
    assessment_grade = models.CharField(
        max_length=32,
        choices=AssessmentGrade.choices,
        verbose_name=_("综合评估等级"),
    )
    remarks = models.TextField(blank=True, default="", verbose_name=_("评估备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    if TYPE_CHECKING:
        evidence_scores: RelatedManager[EvidenceScore]
        jurisdiction_analysis: JurisdictionAnalysis
        litigation_strategy: LitigationStrategy

    class Meta:
        verbose_name = _("案件评估记录")
        verbose_name_plural = _("案件评估记录")
        indexes: ClassVar = [
            models.Index(fields=["assessment_grade"]),
            models.Index(fields=["limitation_status"]),
        ]

    def __str__(self) -> str:
        return f"评估: {self.case} - {self.get_assessment_grade_display()}"
