"""催收工作流 Schema 定义"""

from __future__ import annotations

from datetime import date

from ninja import Schema

# ── 催收工作流 ──


class StartCollectionRequest(Schema):
    """启动催收请求"""

    case_id: int
    start_date: date | None = None
    remarks: str = ""


class AdvanceStageRequest(Schema):
    """推进阶段请求"""

    description: str = ""


class CollectionLogSchema(Schema):
    """催收操作日志"""

    action_type: str
    action_date: date
    description: str
    document_type: str
    document_filename: str


class TimelineNodeSchema(Schema):
    """时间线节点"""

    stage: str
    stage_display: str
    planned_date: date
    is_completed: bool


class CollectionRecordResponse(Schema):
    """催收记录响应"""

    record_id: int
    case_id: int
    current_stage: str
    start_date: date
    last_action_date: date | None
    next_due_date: date | None
    days_elapsed: int
    is_overdue: bool
    remarks: str


class CollectionDetailResponse(CollectionRecordResponse):
    """催收记录详情响应（含日志和时间线）"""

    logs: list[CollectionLogSchema]
    timeline: list[TimelineNodeSchema]


class ReminderItemSchema(Schema):
    """到期提醒项"""

    record_id: int
    case_id: int
    case_name: str
    current_stage: str
    next_due_date: date
    days_until_due: int


# ── 律师函 ──


class LawyerLetterRequest(Schema):
    """律师函生成请求"""

    case_id: int
    tone: str
    creditor_name: str
    debtor_name: str
    principal: float
    interest_amount: float
    contract_no: str = ""
    deadline_days: int = 7


# ── 对账函 ──


class TransactionItemSchema(Schema):
    """交易明细项"""

    transaction_date: date
    description: str
    amount: float


class ReconciliationRequest(Schema):
    """对账函生成请求"""

    case_id: int
    creditor_name: str
    debtor_name: str
    transactions: list[TransactionItemSchema]
    paid_amount: float
    outstanding_amount: float


# ── 和解协议 ──


class InstallmentPlanSchema(Schema):
    """分期还款计划"""

    due_date: date
    amount: float


class SettlementRequest(Schema):
    """和解协议生成请求"""

    case_id: int
    creditor_name: str
    creditor_address: str
    creditor_id_number: str
    debtor_name: str
    debtor_address: str
    debtor_id_number: str
    total_debt: float
    installments: list[InstallmentPlanSchema]
    acceleration_clause: str
    penalty_rate: float
    dispute_resolution: str
    arbitration_institution: str = ""


# ── 执行文书 ──


class EnforcementRequest(Schema):
    """强制执行申请书请求"""

    case_id: int
    applicant_name: str
    applicant_address: str
    applicant_id_number: str
    respondent_name: str
    respondent_address: str
    respondent_id_number: str
    judgment_number: str
    execution_amount: float
    execution_requests: str


class PropertyInvestigationRequest(Schema):
    """财产调查申请书请求"""

    case_id: int
    applicant_name: str
    applicant_address: str
    respondent_name: str
    respondent_address: str
    execution_case_number: str
    property_types: list[str]


class SpendingRestrictionRequest(Schema):
    """限制高消费申请书请求"""

    case_id: int
    applicant_name: str
    applicant_address: str
    respondent_name: str
    respondent_address: str
    legal_representative: str
    execution_case_number: str
    outstanding_amount: float


class AddExecuteeRequest(Schema):
    """追加被执行人申请书请求"""

    case_id: int
    applicant_name: str
    applicant_address: str
    original_respondent_name: str
    original_respondent_address: str
    added_respondent_name: str
    added_respondent_address: str
    added_respondent_id_number: str
    add_reason: str
    legal_basis: str


class ExecutionDocRequest(Schema):
    """执行文书生成请求（统一入口）"""

    doc_type: str
    enforcement: EnforcementRequest | None = None
    property_investigation: PropertyInvestigationRequest | None = None
    spending_restriction: SpendingRestrictionRequest | None = None
    add_executee: AddExecuteeRequest | None = None
