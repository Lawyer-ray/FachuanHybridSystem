from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from django.db import models

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .evidence_score import EvidenceScore
    from .jurisdiction_analysis import JurisdictionAnalysis
    from .litigation_strategy import LitigationStrategy


class ContractBasisType(models.TextChoices):
    WRITTEN = "written", "书面合同"
    ORAL = "oral", "口头约定"
    TRADE_CUSTOM = "trade_custom", "交易习惯"


class LimitationStatus(models.TextChoices):
    NORMAL = "normal", "正常"
    EXPIRING_SOON = "expiring_soon", "即将届满"
    EXPIRED = "expired", "已届满"


class SolvencyRating(models.TextChoices):
    GOOD = "good", "良好"
    FAIR = "fair", "一般"
    POOR = "poor", "较差"
    UNKNOWN = "unknown", "未知"


class AssessmentGrade(models.TextChoices):
    SUFFICIENT = "sufficient", "充分"
    FAIRLY_SUFFICIENT = "fairly_sufficient", "较充分"
    AVERAGE = "average", "一般"
    WEAK = "weak", "薄弱"
    SEVERELY_INSUFFICIENT = "severely_insufficient", "严重不足"


class CaseAssessment(models.Model):
    id: int
    case_id: int
    case: models.OneToOneField[models.Model, models.Model] = models.OneToOneField(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="sales_dispute_assessment",
        verbose_name="关联案件",
    )
    contract_basis: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=ContractBasisType.choices,
        verbose_name="合同基础类型",
    )
    principal_amount: Decimal = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="债权本金")  # type: ignore[assignment]
    evidence_total_score: Decimal = models.DecimalField(  # type: ignore[assignment]
        max_digits=5, decimal_places=2, default=0, verbose_name="证据完整度总分"
    )
    limitation_status: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=LimitationStatus.choices,
        default=LimitationStatus.NORMAL,
        verbose_name="诉讼时效状态",
    )
    limitation_expiry_date: date | None = models.DateField(blank=True, null=True, verbose_name="时效届满日期")  # type: ignore[assignment]
    solvency_rating: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=SolvencyRating.choices,
        default=SolvencyRating.UNKNOWN,
        verbose_name="偿付能力评级",
    )
    assessment_grade: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=AssessmentGrade.choices,
        verbose_name="综合评估等级",
    )
    remarks: str = models.TextField(blank=True, default="", verbose_name="评估备注")  # type: ignore[assignment]
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")  # type: ignore[assignment]
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name="更新时间")  # type: ignore[assignment]

    if TYPE_CHECKING:
        evidence_scores: RelatedManager[EvidenceScore]
        jurisdiction_analysis: JurisdictionAnalysis
        litigation_strategy: LitigationStrategy

    class Meta:
        verbose_name = "案件评估记录"
        verbose_name_plural = "案件评估记录"
        indexes: ClassVar = [
            models.Index(fields=["assessment_grade"]),
            models.Index(fields=["limitation_status"]),
        ]

    def __str__(self) -> str:
        grade_labels = {
            AssessmentGrade.SUFFICIENT.value: "充分",
            AssessmentGrade.FAIRLY_SUFFICIENT.value: "较充分",
            AssessmentGrade.AVERAGE.value: "一般",
            AssessmentGrade.WEAK.value: "薄弱",
            AssessmentGrade.SEVERELY_INSUFFICIENT.value: "严重不足",
        }
        label = grade_labels.get(self.assessment_grade, self.assessment_grade)
        return f"评估: {self.case} - {label}"
