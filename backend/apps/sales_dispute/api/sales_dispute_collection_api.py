"""买卖纠纷计算 API — 催收 + 文书生成端点。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import Router

from apps.sales_dispute.schemas import (
    AdvanceStageRequest,
    CollectionDetailResponse,
    CollectionLogSchema,
    CollectionRecordResponse,
    ExecutionDocRequest,
    LawyerLetterRequest,
    ReconciliationRequest,
    ReminderItemSchema,
    SettlementRequest,
    StartCollectionRequest,
    TimelineNodeSchema,
)

from .sales_dispute_api_factories import (
    _get_collection_reminder,
    _get_collection_workflow,
    _get_execution_doc_generator,
    _get_lawyer_letter_generator,
    _get_reconciliation_generator,
    _get_settlement_generator,
)

router = Router()


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
