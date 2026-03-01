"""
综合评估编排服务

在一个事务中调用4个子服务完成全面案件评估
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.core.exceptions import ValidationException

from .evidence_scorer_service import (
    EvidenceItem,
    EvidenceItemResult,
    EvidenceScorerService,
)
from .jurisdiction_analyzer_service import (
    JurisdictionAnalyzerService,
    JurisdictionParams,
    JurisdictionResult,
)
from .limitation_calculator_service import (
    InterruptionEvent,
    LimitationCalculatorService,
    LimitationCalcParams,
)
from .litigation_strategy_service import (
    LitigationStrategyService,
    StrategyParams,
)

logger = logging.getLogger(__name__)


@dataclass
class AssessmentInput:
    """综合评估输入"""

    case_id: int
    contract_basis: str
    principal_amount: Decimal
    evidence_items: list[EvidenceItem]
    last_claim_date: date
    interruptions: list[InterruptionEvent]
    solvency_rating: str
    has_agreed_jurisdiction: bool
    agreed_court: str
    is_agreed_valid: bool | None
    invalid_reason: str
    plaintiff_location: str
    defendant_location: str
    local_avg_salary: Decimal | None
    willing_to_mediate: bool
    guarantee_debtor: bool = False
    principal_due_date: date | None = None
    remarks: str = ""


@dataclass(frozen=True)
class AssessmentOutput:
    """综合评估输出"""

    assessment_id: int
    case_id: int
    contract_basis: str
    principal_amount: Decimal
    evidence_total_score: Decimal
    evidence_grade: str
    evidence_details: list[EvidenceItemResult]
    limitation_status: str
    limitation_expiry_date: date | None
    remaining_days: int
    risk_warning: str
    guarantee_expiry_date: date | None
    solvency_rating: str
    assessment_grade: str
    jurisdiction: JurisdictionResult
    strategy: dict[str, Any]
    remarks: str


class CaseAssessmentService:
    """综合评估编排服务"""

    def __init__(
        self,
        evidence_scorer: EvidenceScorerService | None = None,
        limitation_calculator: LimitationCalculatorService | None = None,
        jurisdiction_analyzer: JurisdictionAnalyzerService | None = None,
        strategy_recommender: LitigationStrategyService | None = None,
    ) -> None:
        self._evidence_scorer = evidence_scorer or EvidenceScorerService()
        self._limitation_calculator = (
            limitation_calculator or LimitationCalculatorService()
        )
        self._jurisdiction_analyzer = (
            jurisdiction_analyzer or JurisdictionAnalyzerService()
        )
        self._strategy_recommender = (
            strategy_recommender or LitigationStrategyService()
        )

    @transaction.atomic
    def assess(self, input_data: AssessmentInput) -> AssessmentOutput:
        """
        综合评估流程：

        1. 证据评分 → 2. 时效计算 → 3. 管辖权分析 → 4. 策略推荐
        5. 保存/更新数据库记录
        """
        from apps.cases.models import Case
        from apps.sales_dispute.models import (
            CaseAssessment,
            EvidenceScore,
            JurisdictionAnalysis,
            LitigationStrategy,
        )

        if not Case.objects.filter(id=input_data.case_id).exists():
            raise ValidationException(
                message="案件不存在",
                code="CASE_NOT_FOUND",
            )

        # 1. 证据评分
        evidence_result = self._evidence_scorer.calculate(
            input_data.evidence_items
        )

        # 2. 时效计算
        limitation_params = LimitationCalcParams(
            last_claim_date=input_data.last_claim_date,
            interruptions=input_data.interruptions,
            guarantee_debtor=input_data.guarantee_debtor,
            principal_due_date=input_data.principal_due_date,
        )
        limitation_result = self._limitation_calculator.calculate(
            limitation_params
        )

        # 3. 管辖权分析
        jurisdiction_params = JurisdictionParams(
            has_agreed_jurisdiction=input_data.has_agreed_jurisdiction,
            agreed_court=input_data.agreed_court,
            is_agreed_valid=input_data.is_agreed_valid,
            invalid_reason=input_data.invalid_reason,
            plaintiff_location=input_data.plaintiff_location,
            defendant_location=input_data.defendant_location,
        )
        jurisdiction_result = self._jurisdiction_analyzer.analyze(
            jurisdiction_params
        )

        # 4. 策略推荐
        strategy_params = StrategyParams(
            principal_amount=input_data.principal_amount,
            evidence_score=evidence_result.total_score,
            solvency_rating=input_data.solvency_rating,
            local_avg_salary=input_data.local_avg_salary,
            willing_to_mediate=input_data.willing_to_mediate,
        )
        strategy_result = self._strategy_recommender.recommend(strategy_params)

        # 5. 保存/更新 CaseAssessment
        assessment, _created = CaseAssessment.objects.update_or_create(
            case_id=input_data.case_id,
            defaults={
                "contract_basis": input_data.contract_basis,
                "principal_amount": input_data.principal_amount,
                "evidence_total_score": evidence_result.total_score,
                "limitation_status": limitation_result.status,
                "limitation_expiry_date": limitation_result.expiry_date,
                "solvency_rating": input_data.solvency_rating,
                "assessment_grade": evidence_result.grade,
                "remarks": input_data.remarks,
            },
        )

        # 保存证据评分明细（先删后建）
        EvidenceScore.objects.filter(assessment=assessment).delete()
        for detail in evidence_result.details:
            EvidenceScore.objects.create(
                assessment=assessment,
                evidence_type=detail.evidence_type,
                has_evidence=detail.has_evidence,
                quality_score=detail.quality_score,
                remarks="",
            )

        # 保存管辖权分析
        JurisdictionAnalysis.objects.update_or_create(
            assessment=assessment,
            defaults={
                "has_agreed_jurisdiction": jurisdiction_result.has_agreed_jurisdiction,
                "agreed_court": jurisdiction_result.agreed_court,
                "is_agreed_valid": jurisdiction_result.is_agreed_valid,
                "invalid_reason": jurisdiction_result.invalid_reason,
                "plaintiff_location": jurisdiction_result.plaintiff_location,
                "defendant_location": jurisdiction_result.defendant_location,
                "recommended_court": jurisdiction_result.recommended_court,
                "recommendation_reason": jurisdiction_result.recommendation_reason,
                "alternative_court": jurisdiction_result.alternative_court,
                "legal_basis": jurisdiction_result.legal_basis,
            },
        )

        # 保存起诉策略
        LitigationStrategy.objects.update_or_create(
            assessment=assessment,
            defaults={
                "strategy_type": strategy_result.strategy_type,
                "recommendation_reason": strategy_result.recommendation_reason,
                "estimated_duration": strategy_result.estimated_duration,
                "applicable_conditions": strategy_result.applicable_conditions,
                "suggest_preservation": strategy_result.suggest_preservation,
                "preservation_reason": strategy_result.preservation_reason,
            },
        )

        strategy_dict: dict[str, Any] = {
            "strategy_type": strategy_result.strategy_type,
            "recommendation_reason": strategy_result.recommendation_reason,
            "estimated_duration": strategy_result.estimated_duration,
            "applicable_conditions": strategy_result.applicable_conditions,
            "suggest_preservation": strategy_result.suggest_preservation,
            "preservation_reason": strategy_result.preservation_reason,
        }

        return AssessmentOutput(
            assessment_id=assessment.id,
            case_id=input_data.case_id,
            contract_basis=input_data.contract_basis,
            principal_amount=input_data.principal_amount,
            evidence_total_score=evidence_result.total_score,
            evidence_grade=evidence_result.grade,
            evidence_details=evidence_result.details,
            limitation_status=limitation_result.status,
            limitation_expiry_date=limitation_result.expiry_date,
            remaining_days=limitation_result.remaining_days,
            risk_warning=limitation_result.risk_warning,
            guarantee_expiry_date=limitation_result.guarantee_expiry_date,
            solvency_rating=input_data.solvency_rating,
            assessment_grade=evidence_result.grade,
            jurisdiction=jurisdiction_result,
            strategy=strategy_dict,
            remarks=input_data.remarks,
        )

    def get_assessment(self, case_id: int) -> AssessmentOutput:
        """获取已有评估记录"""
        from apps.sales_dispute.models import CaseAssessment

        try:
            assessment = CaseAssessment.objects.select_related(
                "jurisdiction_analysis",
                "litigation_strategy",
            ).prefetch_related(
                "evidence_scores",
            ).get(case_id=case_id)
        except CaseAssessment.DoesNotExist:
            raise ValidationException(
                message="该案件暂无评估记录",
                code="ASSESSMENT_NOT_FOUND",
            )

        evidence_details: list[EvidenceItemResult] = [
            EvidenceItemResult(
                evidence_type=es.evidence_type,
                has_evidence=es.has_evidence,
                quality_score=es.quality_score,
                weight=Decimal("0"),
                weighted_score=Decimal("0"),
            )
            for es in assessment.evidence_scores.all()
        ]

        ja = assessment.jurisdiction_analysis
        jurisdiction = JurisdictionResult(
            has_agreed_jurisdiction=ja.has_agreed_jurisdiction,
            agreed_court=ja.agreed_court,
            is_agreed_valid=ja.is_agreed_valid,
            invalid_reason=ja.invalid_reason,
            plaintiff_location=ja.plaintiff_location,
            defendant_location=ja.defendant_location,
            recommended_court=ja.recommended_court,
            recommendation_reason=ja.recommendation_reason,
            alternative_court=ja.alternative_court,
            legal_basis=ja.legal_basis,
        )

        ls = assessment.litigation_strategy
        strategy_dict: dict[str, Any] = {
            "strategy_type": ls.strategy_type,
            "recommendation_reason": ls.recommendation_reason,
            "estimated_duration": ls.estimated_duration,
            "applicable_conditions": ls.applicable_conditions,
            "suggest_preservation": ls.suggest_preservation,
            "preservation_reason": ls.preservation_reason,
        }

        return AssessmentOutput(
            assessment_id=assessment.id,
            case_id=case_id,
            contract_basis=assessment.contract_basis,
            principal_amount=assessment.principal_amount,
            evidence_total_score=assessment.evidence_total_score,
            evidence_grade=assessment.assessment_grade,
            evidence_details=evidence_details,
            limitation_status=assessment.limitation_status,
            limitation_expiry_date=assessment.limitation_expiry_date,
            remaining_days=0,
            risk_warning="",
            guarantee_expiry_date=None,
            solvency_rating=assessment.solvency_rating,
            assessment_grade=assessment.assessment_grade,
            jurisdiction=jurisdiction,
            strategy=strategy_dict,
            remarks=assessment.remarks,
        )
