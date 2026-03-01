"""案件评估记录 Admin 配置"""

from __future__ import annotations

from django.contrib import admin

from apps.cases.admin.base import (
    BaseModelAdmin,
    BaseStackedInline,
    BaseTabularInline,
)
from apps.sales_dispute.models import (
    CaseAssessment,
    EvidenceScore,
    JurisdictionAnalysis,
    LitigationStrategy,
)


class EvidenceScoreInline(BaseTabularInline):
    """证据评分明细 Inline"""

    model = EvidenceScore
    extra = 0


class JurisdictionAnalysisInline(BaseStackedInline):
    """管辖权分析 Inline"""

    model = JurisdictionAnalysis
    extra = 0
    max_num = 1


class LitigationStrategyInline(BaseStackedInline):
    """起诉策略推荐 Inline"""

    model = LitigationStrategy
    extra = 0
    max_num = 1


@admin.register(CaseAssessment)
class CaseAssessmentAdmin(BaseModelAdmin):
    """案件评估记录 Admin"""

    list_display = (
        "case",
        "contract_basis",
        "principal_amount",
        "evidence_total_score",
        "limitation_status",
        "assessment_grade",
        "created_at",
    )
    list_filter = ("assessment_grade", "limitation_status")
    search_fields = ("case__name",)
    inlines = [
        EvidenceScoreInline,
        JurisdictionAnalysisInline,
        LitigationStrategyInline,
    ]
