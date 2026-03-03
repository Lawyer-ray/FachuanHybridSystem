"""
买卖纠纷计算 API 端点

工厂函数 + 参数提取，float ↔ Decimal 在此边界层转换。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _
from ninja import Query, Router
from ninja.errors import HttpError

from apps.sales_dispute.schemas import (
    AdvanceStageRequest,
    AssessmentRequest,
    AssessmentResponse,
    BreakdownItemResponse,
    BreakdownQuery,
    BreakdownResponse,
    CaseStatsResponse,
    CollectionDetailResponse,
    CollectionLogSchema,
    CollectionRecordResponse,
    CostBenefitRequest,
    CostBenefitResponse,
    DateRangeQuery,
    EvidenceItemResponse,
    ExecutionDocRequest,
    FactorGroupResponse,
    FactorsResponse,
    InterestCalcRequest,
    InterestCalcResponse,
    JurisdictionRequest,
    JurisdictionResponseSchema,
    LawyerLetterRequest,
    LawyerPerformanceItemResponse,
    LawyerPerformanceQuery,
    LawyerPerformanceResponse,
    LimitationRequest,
    LimitationResponse,
    LPRRateResponse,
    QueryPeriodSchema,
    ReconciliationRequest,
    ReminderItemSchema,
    SegmentDetailResponse,
    SettlementRequest,
    StartCollectionRequest,
    StrategyRequest,
    StrategyResponseSchema,
    SummaryResponse,
    TimelineNodeSchema,
    TrendItemResponse,
    TrendQuery,
    TrendResponse,
)

logger = logging.getLogger(__name__)

router = Router()


# ── 工厂函数 ──────────────────────────────────────────────


def _get_interest_calculator() -> Any:
    from apps.sales_dispute.services.interest_calculator_service import InterestCalculatorService

    return InterestCalculatorService()


def _get_cost_benefit_service() -> Any:
    from apps.sales_dispute.services.cost_benefit_service import CostBenefitService

    return CostBenefitService()


def _get_lpr_rate_service() -> Any:
    from apps.sales_dispute.services.lpr_rate_service import LprRateService

    return LprRateService()


def _get_case_assessment_service() -> Any:
    from apps.sales_dispute.services.case_assessment_service import CaseAssessmentService

    return CaseAssessmentService()


def _get_limitation_calculator() -> Any:
    from apps.sales_dispute.services.limitation_calculator_service import LimitationCalculatorService

    return LimitationCalculatorService()


def _get_jurisdiction_analyzer() -> Any:
    from apps.sales_dispute.services.jurisdiction_analyzer_service import JurisdictionAnalyzerService

    return JurisdictionAnalyzerService()


def _get_strategy_recommender() -> Any:
    from apps.sales_dispute.services.litigation_strategy_service import LitigationStrategyService

    return LitigationStrategyService()


def _get_collection_workflow() -> Any:
    from apps.sales_dispute.services.collection_workflow_service import CollectionWorkflowService

    return CollectionWorkflowService()


def _get_collection_reminder() -> Any:
    from apps.sales_dispute.services.collection_reminder_service import CollectionReminderService

    return CollectionReminderService()


def _get_lawyer_letter_generator() -> Any:
    from apps.sales_dispute.services.lawyer_letter_generator_service import LawyerLetterGeneratorService

    return LawyerLetterGeneratorService()


def _get_reconciliation_generator() -> Any:
    from apps.sales_dispute.services.reconciliation_generator_service import ReconciliationGeneratorService

    return ReconciliationGeneratorService()


def _get_settlement_generator() -> Any:
    from apps.sales_dispute.services.settlement_generator_service import SettlementGeneratorService

    return SettlementGeneratorService()


def _get_execution_doc_generator() -> Any:
    from apps.sales_dispute.services.execution_doc_generator_service import ExecutionDocGeneratorService

    return ExecutionDocGeneratorService()


def _get_dashboard_service() -> Any:
    from apps.sales_dispute.services.dashboard_service import DashboardService

    return DashboardService()


def _resolve_date_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    """未提供日期时默认当前自然年"""
    today = date.today()
    return (
        start_date or date(today.year, 1, 1),
        end_date or date(today.year, 12, 31),
    )


# ── API 端点 ──────────────────────────────────────────────


@router.post("/calculate-interest", response=InterestCalcResponse)
def calculate_interest(
    request: HttpRequest,
    data: InterestCalcRequest,
) -> InterestCalcResponse:
    """利息/违约金计算"""
    from apps.sales_dispute.services.interest_calculator_service import (
        BatchDelivery,
        InterestCalcParams,
        InterestStartType,
        RateType,
    )

    batch_deliveries: list[BatchDelivery] | None = None
    if data.batch_deliveries:
        batch_deliveries = [
            BatchDelivery(
                delivery_date=item.delivery_date,
                amount=Decimal(str(item.amount)),
                payment_date=item.payment_date,
            )
            for item in data.batch_deliveries
        ]

    params = InterestCalcParams(
        principal=Decimal(str(data.principal)),
        start_date=data.start_date,
        end_date=data.end_date,
        rate_type=RateType(data.rate_type),
        agreed_rate=Decimal(str(data.agreed_rate)) if data.agreed_rate is not None else None,
        penalty_amount=Decimal(str(data.penalty_amount)) if data.penalty_amount is not None else None,
        penalty_daily_rate=Decimal(str(data.penalty_daily_rate)) if data.penalty_daily_rate is not None else None,
        lpr_markup=Decimal(str(data.lpr_markup)),
        interest_start_type=InterestStartType(data.interest_start_type),
        agreed_payment_date=data.agreed_payment_date,
        demand_date=data.demand_date,
        reasonable_period_days=data.reasonable_period_days,
        batch_deliveries=batch_deliveries,
    )

    svc = _get_interest_calculator()
    result = svc.calculate(params)

    segments = [
        SegmentDetailResponse(
            start_date=seg.start_date,
            end_date=seg.end_date,
            days=seg.days,
            rate=float(seg.rate),
            interest=float(seg.interest),
        )
        for seg in result.segments
    ]

    return InterestCalcResponse(
        total_interest=float(result.total_interest),
        segments=segments,
        warnings=result.warnings,
    )


@router.post("/calculate-cost", response=CostBenefitResponse)
def calculate_cost(
    request: HttpRequest,
    data: CostBenefitRequest,
) -> CostBenefitResponse:
    """成本收益分析"""
    from apps.sales_dispute.services.cost_benefit_service import CostBenefitParams

    params = CostBenefitParams(
        principal=Decimal(str(data.principal)),
        interest_amount=Decimal(str(data.interest_amount)),
        lawyer_fee=Decimal(str(data.lawyer_fee)),
        preservation_amount=Decimal(str(data.preservation_amount)),
        guarantee_rate=Decimal(str(data.guarantee_rate)),
        notary_fee=Decimal(str(data.notary_fee)),
        case_type=data.case_type,
        cause_of_action=data.cause_of_action,
        recovery_rate=Decimal(str(data.recovery_rate)),
        support_rate=Decimal(str(data.support_rate)),
        fee_transfer_rate=Decimal(str(data.fee_transfer_rate)),
        lawyer_transfer_rate=Decimal(str(data.lawyer_transfer_rate)),
    )

    svc = _get_cost_benefit_service()
    result = svc.analyze(params)

    return CostBenefitResponse(
        total_cost=float(result.total_cost),
        total_revenue=float(result.total_revenue),
        net_profit=float(result.net_profit),
        roi=float(result.roi),
        cost_details={k: float(v) for k, v in result.cost_details.items()},
        revenue_details={k: float(v) for k, v in result.revenue_details.items()},
        risk_warning=result.risk_warning,
    )


@router.get("/lpr-rates", response=list[LPRRateResponse])
def list_lpr_rates(request: HttpRequest) -> list[LPRRateResponse]:
    """获取LPR利率历史数据"""
    svc = _get_lpr_rate_service()
    rates = svc.get_all_rates()

    return [
        LPRRateResponse(
            effective_date=rate.effective_date,
            rate_1y=float(rate.rate_1y),
            rate_5y=float(rate.rate_5y),
        )
        for rate in rates
    ]


# ── 案件评估端点 ──────────────────────────────────────────


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


@router.post("/calculate-limitation", response=LimitationResponse)
def calculate_limitation(
    request: HttpRequest,
    data: LimitationRequest,
) -> LimitationResponse:
    """诉讼时效计算"""
    from apps.sales_dispute.services.limitation_calculator_service import (
        InterruptionEvent,
        InterruptionType,
        LimitationCalcParams,
    )

    interruptions = [
        InterruptionEvent(
            event_type=InterruptionType(evt.event_type),
            event_date=evt.event_date,
        )
        for evt in data.interruptions
    ]

    params = LimitationCalcParams(
        last_claim_date=data.last_claim_date,
        interruptions=interruptions,
        guarantee_debtor=data.guarantee_debtor,
        principal_due_date=data.principal_due_date,
    )

    svc = _get_limitation_calculator()
    result = svc.calculate(params)

    return LimitationResponse(
        status=result.status,
        expiry_date=result.expiry_date,
        remaining_days=result.remaining_days,
        base_date=result.base_date,
        risk_warning=result.risk_warning,
        guarantee_expiry_date=result.guarantee_expiry_date,
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


# ── 催收工作流端点 ──────────────────────────────────────────


@router.post("/collection/start", response=CollectionRecordResponse)
def start_collection(
    request: HttpRequest,
    data: StartCollectionRequest,
) -> CollectionRecordResponse:
    """启动催收"""
    svc = _get_collection_workflow()
    result = svc.start_collection(
        case_id=data.case_id,
        start_date=data.start_date,
        remarks=data.remarks,
    )

    return CollectionRecordResponse(
        record_id=result.record_id,
        case_id=result.case_id,
        current_stage=result.current_stage,
        start_date=result.start_date,
        last_action_date=result.last_action_date,
        next_due_date=result.next_due_date,
        days_elapsed=result.days_elapsed,
        is_overdue=result.is_overdue,
        remarks=result.remarks,
    )


@router.post("/collection/{record_id}/advance", response=CollectionRecordResponse)
def advance_collection(
    request: HttpRequest,
    record_id: int,
    data: AdvanceStageRequest,
) -> CollectionRecordResponse:
    """推进催收阶段"""
    svc = _get_collection_workflow()
    result = svc.advance_stage(
        record_id=record_id,
        description=data.description,
    )

    return CollectionRecordResponse(
        record_id=result.record_id,
        case_id=result.case_id,
        current_stage=result.current_stage,
        start_date=result.start_date,
        last_action_date=result.last_action_date,
        next_due_date=result.next_due_date,
        days_elapsed=result.days_elapsed,
        is_overdue=result.is_overdue,
        remarks=result.remarks,
    )


@router.get("/collection/reminders", response=list[ReminderItemSchema])
def get_reminders(
    request: HttpRequest,
    days_ahead: int = 7,
) -> list[ReminderItemSchema]:
    """获取即将到期的催收节点"""
    svc = _get_collection_reminder()
    items = svc.get_upcoming_reminders(days_ahead=days_ahead)

    return [
        ReminderItemSchema(
            record_id=item.record_id,
            case_id=item.case_id,
            case_name=item.case_name,
            current_stage=item.current_stage,
            next_due_date=item.next_due_date,
            days_until_due=item.days_until_due,
        )
        for item in items
    ]


# ── 文书生成端点（返回 HttpResponse 下载） ──────────────────
# NOTE: generate-* 路由必须在 {case_id} 路由之前注册，避免路径参数抢先匹配


@router.post("/collection/generate-lawyer-letter")
def generate_lawyer_letter(
    request: HttpRequest,
    data: LawyerLetterRequest,
) -> HttpResponse:
    """生成律师函"""
    from apps.sales_dispute.services.lawyer_letter_generator_service import LawyerLetterParams, LetterTone

    params = LawyerLetterParams(
        case_id=data.case_id,
        tone=LetterTone(data.tone),
        creditor_name=data.creditor_name,
        debtor_name=data.debtor_name,
        principal=Decimal(str(data.principal)),
        interest_amount=Decimal(str(data.interest_amount)),
        contract_no=data.contract_no,
        deadline_days=data.deadline_days,
    )

    svc = _get_lawyer_letter_generator()
    doc = svc.generate(params)

    response = HttpResponse(
        doc.content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{doc.filename}"'
    return response


@router.post("/collection/generate-reconciliation")
def generate_reconciliation(
    request: HttpRequest,
    data: ReconciliationRequest,
) -> HttpResponse:
    """生成对账函"""
    from apps.sales_dispute.services.reconciliation_generator_service import ReconciliationParams, TransactionItem

    transactions = [
        TransactionItem(
            transaction_date=item.transaction_date,
            description=item.description,
            amount=Decimal(str(item.amount)),
        )
        for item in data.transactions
    ]

    params = ReconciliationParams(
        case_id=data.case_id,
        creditor_name=data.creditor_name,
        debtor_name=data.debtor_name,
        transactions=transactions,
        paid_amount=Decimal(str(data.paid_amount)),
        outstanding_amount=Decimal(str(data.outstanding_amount)),
    )

    svc = _get_reconciliation_generator()
    doc = svc.generate(params)

    response = HttpResponse(
        doc.content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{doc.filename}"'
    return response


@router.post("/collection/generate-settlement")
def generate_settlement(
    request: HttpRequest,
    data: SettlementRequest,
) -> HttpResponse:
    """生成和解协议"""
    from apps.sales_dispute.services.settlement_generator_service import (
        DisputeResolution,
        InstallmentPlan,
        SettlementParams,
    )

    installments = [
        InstallmentPlan(
            due_date=item.due_date,
            amount=Decimal(str(item.amount)),
        )
        for item in data.installments
    ]

    params = SettlementParams(
        case_id=data.case_id,
        creditor_name=data.creditor_name,
        creditor_address=data.creditor_address,
        creditor_id_number=data.creditor_id_number,
        debtor_name=data.debtor_name,
        debtor_address=data.debtor_address,
        debtor_id_number=data.debtor_id_number,
        total_debt=Decimal(str(data.total_debt)),
        installments=installments,
        acceleration_clause=data.acceleration_clause,
        penalty_rate=Decimal(str(data.penalty_rate)),
        dispute_resolution=DisputeResolution(data.dispute_resolution),
        arbitration_institution=data.arbitration_institution,
    )

    svc = _get_settlement_generator()
    doc = svc.generate(params)

    response = HttpResponse(
        doc.content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{doc.filename}"'
    return response


@router.post("/collection/generate-execution-doc")
def generate_execution_doc(
    request: HttpRequest,
    data: ExecutionDocRequest,
) -> HttpResponse:
    """生成执行阶段文书"""
    from apps.sales_dispute.services.execution_doc_generator_service import (
        AddExecuteeParams,
        EnforcementParams,
        ExecutionDocType,
        PropertyInvestigationParams,
        SpendingRestrictionParams,
    )

    svc = _get_execution_doc_generator()
    doc_type = ExecutionDocType(data.doc_type)

    if doc_type == ExecutionDocType.ENFORCEMENT:
        assert data.enforcement is not None
        params_enf = EnforcementParams(
            case_id=data.enforcement.case_id,
            applicant_name=data.enforcement.applicant_name,
            applicant_address=data.enforcement.applicant_address,
            applicant_id_number=data.enforcement.applicant_id_number,
            respondent_name=data.enforcement.respondent_name,
            respondent_address=data.enforcement.respondent_address,
            respondent_id_number=data.enforcement.respondent_id_number,
            judgment_number=data.enforcement.judgment_number,
            execution_amount=Decimal(str(data.enforcement.execution_amount)),
            execution_requests=data.enforcement.execution_requests,
        )
        doc = svc.generate_enforcement(params_enf)

    elif doc_type == ExecutionDocType.PROPERTY_INVESTIGATION:
        assert data.property_investigation is not None
        params_pi = PropertyInvestigationParams(
            case_id=data.property_investigation.case_id,
            applicant_name=data.property_investigation.applicant_name,
            applicant_address=data.property_investigation.applicant_address,
            respondent_name=data.property_investigation.respondent_name,
            respondent_address=data.property_investigation.respondent_address,
            execution_case_number=data.property_investigation.execution_case_number,
            property_types=data.property_investigation.property_types,
        )
        doc = svc.generate_property_investigation(params_pi)

    elif doc_type == ExecutionDocType.SPENDING_RESTRICTION:
        assert data.spending_restriction is not None
        params_sr = SpendingRestrictionParams(
            case_id=data.spending_restriction.case_id,
            applicant_name=data.spending_restriction.applicant_name,
            applicant_address=data.spending_restriction.applicant_address,
            respondent_name=data.spending_restriction.respondent_name,
            respondent_address=data.spending_restriction.respondent_address,
            legal_representative=data.spending_restriction.legal_representative,
            execution_case_number=data.spending_restriction.execution_case_number,
            outstanding_amount=Decimal(str(data.spending_restriction.outstanding_amount)),
        )
        doc = svc.generate_spending_restriction(params_sr)

    else:
        assert data.add_executee is not None
        params_ae = AddExecuteeParams(
            case_id=data.add_executee.case_id,
            applicant_name=data.add_executee.applicant_name,
            applicant_address=data.add_executee.applicant_address,
            original_respondent_name=data.add_executee.original_respondent_name,
            original_respondent_address=data.add_executee.original_respondent_address,
            added_respondent_name=data.add_executee.added_respondent_name,
            added_respondent_address=data.add_executee.added_respondent_address,
            added_respondent_id_number=data.add_executee.added_respondent_id_number,
            add_reason=data.add_executee.add_reason,
            legal_basis=data.add_executee.legal_basis,
        )
        doc = svc.generate_add_executee(params_ae)

    response = HttpResponse(
        doc.content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{doc.filename}"'
    return response


# ── 看板端点 ──────────────────────────────────────────────


@router.get("/dashboard/summary", response=SummaryResponse)
def get_dashboard_summary(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """核心指标统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    out = svc.get_summary(s, e)
    return SummaryResponse(
        total_recovery=str(out.total_recovery),
        recovery_rate=str(out.recovery_rate),
        avg_recovery_cycle=out.avg_recovery_cycle,
        recovered_case_count=out.recovered_case_count,
        unrecovered_case_count=out.unrecovered_case_count,
        query_period=QueryPeriodSchema(start_date=out.query_start, end_date=out.query_end),
    )


@router.get("/dashboard/trend", response=TrendResponse)
def get_dashboard_trend(
    request: HttpRequest,
    query: Query[TrendQuery],
) -> Any:
    """回款趋势"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_dims = {"month", "quarter", "year"}
    if query.dimension not in valid_dims:
        raise HttpError(422, _("时间维度参数无效，可选值：month, quarter, year"))
    svc = _get_dashboard_service()
    items = svc.get_trend(s, e, query.dimension)
    return TrendResponse(
        items=[
            TrendItemResponse(
                label=it.label,
                amount=str(it.amount),
                count=it.count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/breakdown", response=BreakdownResponse)
def get_dashboard_breakdown(
    request: HttpRequest,
    query: Query[BreakdownQuery],
) -> Any:
    """多维度分组统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_groups = {"case_type", "amount_range", "lawyer"}
    if query.group_by not in valid_groups:
        raise HttpError(422, _("分组参数无效，可选值：case_type, amount_range, lawyer"))
    svc = _get_dashboard_service()
    items = svc.get_breakdown(s, e, query.group_by)
    return BreakdownResponse(
        items=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/factors", response=FactorsResponse)
def get_dashboard_factors(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """回款影响因素分析"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    result = svc.get_factors(s, e)

    def _to_factor_resp(items: list[Any]) -> list[FactorGroupResponse]:
        return [
            FactorGroupResponse(
                group_label=it.group_label,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ]

    return FactorsResponse(
        debt_age=_to_factor_resp(result["debt_age"]),
        contract_basis=_to_factor_resp(result["contract_basis"]),
        preservation=_to_factor_resp(result["preservation"]),
        amount_range=_to_factor_resp(result["amount_range"]),
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/lawyer-performance", response=LawyerPerformanceResponse)
def get_dashboard_lawyer_performance(
    request: HttpRequest,
    query: Query[LawyerPerformanceQuery],
) -> Any:
    """律师绩效分析"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_sorts = {"total_recovery", "recovery_rate", "case_count"}
    if query.sort_by not in valid_sorts:
        raise HttpError(422, _("排序参数无效，可选值：total_recovery, recovery_rate, case_count"))
    svc = _get_dashboard_service()
    items = svc.get_lawyer_performance(s, e, query.sort_by)
    return LawyerPerformanceResponse(
        items=[
            LawyerPerformanceItemResponse(
                lawyer_id=it.lawyer_id,
                lawyer_name=it.lawyer_name,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
                avg_recovery_cycle=it.avg_recovery_cycle,
                closed_rate=str(it.closed_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/case-stats", response=CaseStatsResponse)
def get_dashboard_case_stats(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """案件数据统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    out = svc.get_case_stats(s, e)
    return CaseStatsResponse(
        total_cases=out.total_cases,
        active_cases=out.active_cases,
        closed_cases=out.closed_cases,
        stage_distribution=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.stage_distribution
        ],
        amount_distribution=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.amount_distribution
        ],
        stage_conversion_rates=[
            FactorGroupResponse(
                group_label=it.group_label,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.stage_conversion_rates
        ],
        query_period=QueryPeriodSchema(start_date=out.query_start, end_date=out.query_end),
    )


# ── 催收记录详情（{case_id} 路径参数路由放在最后，避免抢先匹配） ──


@router.get("/collection/{case_id}", response=CollectionDetailResponse)
def get_collection(
    request: HttpRequest,
    case_id: int,
) -> CollectionDetailResponse:
    """获取催收记录详情（含日志和时间线）"""
    workflow = _get_collection_workflow()
    reminder = _get_collection_reminder()

    record = workflow.get_collection(case_id)
    timeline = reminder.get_timeline(record.record_id)
    logs = workflow.get_logs(record.record_id)

    return CollectionDetailResponse(
        record_id=record.record_id,
        case_id=record.case_id,
        current_stage=record.current_stage,
        start_date=record.start_date,
        last_action_date=record.last_action_date,
        next_due_date=record.next_due_date,
        days_elapsed=record.days_elapsed,
        is_overdue=record.is_overdue,
        remarks=record.remarks,
        logs=[
            CollectionLogSchema(
                action_type=log["action_type"],
                action_date=log["action_date"],
                description=log["description"],
                document_type=log["document_type"],
                document_filename=log["document_filename"],
            )
            for log in logs
        ],
        timeline=[
            TimelineNodeSchema(
                stage=node.stage,
                stage_display=node.stage_display,
                planned_date=node.planned_date,
                is_completed=node.is_completed,
            )
            for node in timeline
        ],
    )
