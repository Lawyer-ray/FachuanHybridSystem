"""买卖纠纷计算 API — 案件评估/管辖/策略端点。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.sales_dispute.schemas import (
    AssessmentRequest,
    AssessmentResponse,
    EvidenceItemResponse,
    JurisdictionRequest,
    JurisdictionResponseSchema,
    StrategyRequest,
    StrategyResponseSchema,
)

from .sales_dispute_api_factories import (
    _get_case_assessment_service,
    _get_jurisdiction_analyzer,
    _get_strategy_recommender,
)

router = Router()


@router.post("/assess", response=AssessmentResponse)
def assess_case(
    request: HttpRequest,
    data: AssessmentRequest,
) -> AssessmentResponse:
    """综合案件评估"""
    from apps.sales_dispute.services.case_assessment_service import AssessmentInput
    from apps.sales_dispute.services.evidence_scorer_service import EvidenceItem
    from apps.sales_dispute.services.limitation_calculator_service import InterruptionEvent, InterruptionType

    evidence_items = [
        EvidenceItem(
            evidence_type=item.evidence_type,
            has_evidence=item.has_evidence,
            quality_score=item.quality_score,
        )
        for item in data.evidence_items
    ]

    interruptions = [
        InterruptionEvent(
            event_type=InterruptionType(evt.event_type),
            event_date=evt.event_date,
        )
        for evt in data.interruptions
    ]

    input_data = AssessmentInput(
        case_id=data.case_id,
        contract_basis=data.contract_basis,
        principal_amount=Decimal(str(data.principal_amount)),
        evidence_items=evidence_items,
        last_claim_date=data.last_claim_date,
        interruptions=interruptions,
        solvency_rating=data.solvency_rating,
        has_agreed_jurisdiction=data.has_agreed_jurisdiction,
        agreed_court=data.agreed_court,
        is_agreed_valid=data.is_agreed_valid,
        invalid_reason=data.invalid_reason,
        plaintiff_location=data.plaintiff_location,
        defendant_location=data.defendant_location,
        local_avg_salary=(Decimal(str(data.local_avg_salary)) if data.local_avg_salary is not None else None),
        willing_to_mediate=data.willing_to_mediate,
        guarantee_debtor=data.guarantee_debtor,
        principal_due_date=data.principal_due_date,
        remarks=data.remarks,
    )

    svc = _get_case_assessment_service()
    result = svc.assess(input_data)

    return AssessmentResponse(
        assessment_id=result.assessment_id,
        case_id=result.case_id,
        contract_basis=result.contract_basis,
        principal_amount=float(result.principal_amount),
        evidence_total_score=float(result.evidence_total_score),
        evidence_grade=result.evidence_grade,
        evidence_details=[
            EvidenceItemResponse(
                evidence_type=d.evidence_type,
                has_evidence=d.has_evidence,
                quality_score=d.quality_score,
                weight=float(d.weight),
                weighted_score=float(d.weighted_score),
            )
            for d in result.evidence_details
        ],
        limitation_status=result.limitation_status,
        limitation_expiry_date=result.limitation_expiry_date,
        remaining_days=result.remaining_days,
        risk_warning=result.risk_warning,
        guarantee_expiry_date=result.guarantee_expiry_date,
        solvency_rating=result.solvency_rating,
        assessment_grade=result.assessment_grade,
        jurisdiction=JurisdictionResponseSchema(
            has_agreed_jurisdiction=result.jurisdiction.has_agreed_jurisdiction,
            agreed_court=result.jurisdiction.agreed_court,
            is_agreed_valid=result.jurisdiction.is_agreed_valid,
            invalid_reason=result.jurisdiction.invalid_reason,
            plaintiff_location=result.jurisdiction.plaintiff_location,
            defendant_location=result.jurisdiction.defendant_location,
            recommended_court=result.jurisdiction.recommended_court,
            recommendation_reason=result.jurisdiction.recommendation_reason,
            alternative_court=result.jurisdiction.alternative_court,
            legal_basis=result.jurisdiction.legal_basis,
        ),
        strategy=StrategyResponseSchema(
            strategy_type=result.strategy["strategy_type"],
            recommendation_reason=result.strategy["recommendation_reason"],
            estimated_duration=result.strategy["estimated_duration"],
            applicable_conditions=result.strategy["applicable_conditions"],
            suggest_preservation=result.strategy["suggest_preservation"],
            preservation_reason=result.strategy["preservation_reason"],
        ),
        remarks=result.remarks,
    )


@router.get("/assess/{case_id}", response=AssessmentResponse)
def get_assessment(
    request: HttpRequest,
    case_id: int,
) -> AssessmentResponse:
    """获取已有评估记录"""
    svc = _get_case_assessment_service()
    result = svc.get_assessment(case_id)

    return AssessmentResponse(
        assessment_id=result.assessment_id,
        case_id=result.case_id,
        contract_basis=result.contract_basis,
        principal_amount=float(result.principal_amount),
        evidence_total_score=float(result.evidence_total_score),
        evidence_grade=result.evidence_grade,
        evidence_details=[
            EvidenceItemResponse(
                evidence_type=d.evidence_type,
                has_evidence=d.has_evidence,
                quality_score=d.quality_score,
                weight=float(d.weight),
                weighted_score=float(d.weighted_score),
            )
            for d in result.evidence_details
        ],
        limitation_status=result.limitation_status,
        limitation_expiry_date=result.limitation_expiry_date,
        remaining_days=result.remaining_days,
        risk_warning=result.risk_warning,
        guarantee_expiry_date=result.guarantee_expiry_date,
        solvency_rating=result.solvency_rating,
        assessment_grade=result.assessment_grade,
        jurisdiction=JurisdictionResponseSchema(
            has_agreed_jurisdiction=result.jurisdiction.has_agreed_jurisdiction,
            agreed_court=result.jurisdiction.agreed_court,
            is_agreed_valid=result.jurisdiction.is_agreed_valid,
            invalid_reason=result.jurisdiction.invalid_reason,
            plaintiff_location=result.jurisdiction.plaintiff_location,
            defendant_location=result.jurisdiction.defendant_location,
            recommended_court=result.jurisdiction.recommended_court,
            recommendation_reason=result.jurisdiction.recommendation_reason,
            alternative_court=result.jurisdiction.alternative_court,
            legal_basis=result.jurisdiction.legal_basis,
        ),
        strategy=StrategyResponseSchema(
            strategy_type=result.strategy["strategy_type"],
            recommendation_reason=result.strategy["recommendation_reason"],
            estimated_duration=result.strategy["estimated_duration"],
            applicable_conditions=result.strategy["applicable_conditions"],
            suggest_preservation=result.strategy["suggest_preservation"],
            preservation_reason=result.strategy["preservation_reason"],
        ),
        remarks=result.remarks,
    )


@router.post("/analyze-jurisdiction", response=JurisdictionResponseSchema)
def analyze_jurisdiction(
    request: HttpRequest,
    data: JurisdictionRequest,
) -> JurisdictionResponseSchema:
    """管辖权分析"""
    from apps.sales_dispute.services.jurisdiction_analyzer_service import JurisdictionParams

    params = JurisdictionParams(
        has_agreed_jurisdiction=data.has_agreed_jurisdiction,
        agreed_court=data.agreed_court,
        is_agreed_valid=data.is_agreed_valid,
        invalid_reason=data.invalid_reason,
        plaintiff_location=data.plaintiff_location,
        defendant_location=data.defendant_location,
    )

    svc = _get_jurisdiction_analyzer()
    result = svc.analyze(params)

    return JurisdictionResponseSchema(
        has_agreed_jurisdiction=result.has_agreed_jurisdiction,
        agreed_court=result.agreed_court,
        is_agreed_valid=result.is_agreed_valid,
        invalid_reason=result.invalid_reason,
        plaintiff_location=result.plaintiff_location,
        defendant_location=result.defendant_location,
        recommended_court=result.recommended_court,
        recommendation_reason=result.recommendation_reason,
        alternative_court=result.alternative_court,
        legal_basis=result.legal_basis,
    )


@router.post("/recommend-strategy", response=StrategyResponseSchema)
def recommend_strategy(
    request: HttpRequest,
    data: StrategyRequest,
) -> StrategyResponseSchema:
    """起诉策略推荐"""
    from apps.sales_dispute.services.litigation_strategy_service import StrategyParams

    params = StrategyParams(
        principal_amount=Decimal(str(data.principal_amount)),
        evidence_score=Decimal(str(data.evidence_score)),
        solvency_rating=data.solvency_rating,
        local_avg_salary=(Decimal(str(data.local_avg_salary)) if data.local_avg_salary is not None else None),
        willing_to_mediate=data.willing_to_mediate,
    )

    svc = _get_strategy_recommender()
    result = svc.recommend(params)

    return StrategyResponseSchema(
        strategy_type=result.strategy_type,
        recommendation_reason=result.recommendation_reason,
        estimated_duration=result.estimated_duration,
        applicable_conditions=result.applicable_conditions,
        suggest_preservation=result.suggest_preservation,
        preservation_reason=result.preservation_reason,
    )
