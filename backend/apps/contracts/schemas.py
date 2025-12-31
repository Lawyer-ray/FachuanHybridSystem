from ninja import Schema, ModelSchema
from typing import Optional, List
from pydantic import model_validator, field_validator
from .models import (
    Contract, FeeMode, ContractParty, ContractPayment, InvoiceStatus, 
    ContractReminder, SupplementaryAgreement, SupplementaryAgreementParty, PartyRole
)
from apps.core.enums import CaseStage
from apps.cases.schemas import CaseOut
from apps.organization.schemas import LawyerOut
from apps.client.schemas import ClientOut
from apps.core.schemas import SchemaMixin


class ContractPartySourceOut(Schema):
    """合同当事人（含来源）输出 Schema
    
    用于 API 端点 /contracts/{contract_id}/all-parties/
    返回合同及其补充协议的所有当事人
    
    Requirements: 5.2, 5.4
    """
    id: int           # Client ID
    name: str         # Client 名称
    source: str       # 来源: "contract" | "supplementary"
    role: Optional[str] = None  # 当事人角色: "PRINCIPAL" | "BENEFICIARY" | "OPPOSING"


class SupplementaryAgreementPartyInput(Schema):
    """补充协议当事人输入（用于嵌套）"""
    client_id: int
    role: str = "PRINCIPAL"


class SupplementaryAgreementInput(Schema):
    """补充协议输入（用于嵌套在合同创建/更新中）"""
    name: Optional[str] = None
    party_ids: Optional[List[int]] = None  # 兼容旧接口
    parties: Optional[List[SupplementaryAgreementPartyInput]] = None  # 新接口（含身份）


class UpdateLawyersIn(Schema):
    """更新合同律师指派输入 Schema"""
    lawyer_ids: List[int]
    
    @field_validator("lawyer_ids")
    @classmethod
    def validate_lawyer_ids(cls, v):
        """验证律师 ID 列表非空"""
        if not v:
            raise ValueError("至少需要指派一个律师")
        return v


class ContractPartyIn(Schema):
    """合同当事人输入"""
    client_id: int
    role: str = PartyRole.PRINCIPAL


class ContractIn(ModelSchema):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    fee_mode: Optional[str] = FeeMode.FIXED
    fixed_amount: Optional[float] = None
    risk_rate: Optional[float] = None
    custom_terms: Optional[str] = None
    lawyer_ids: List[int]  # 律师 ID 列表，第一个为主办律师
    parties: Optional[List[ContractPartyIn]] = None  # 当事人列表（含身份）
    supplementary_agreements: Optional[List[SupplementaryAgreementInput]] = None  # 补充协议列表

    class Meta:
        model = Contract
        fields = [
            "name",
            "case_type",
            "status",
            "start_date",
            "end_date",
            "is_archived",
            "fee_mode",
            "fixed_amount",
            "risk_rate",
            "custom_terms",
            "representation_stages",
        ]

    @field_validator("lawyer_ids")
    @classmethod
    def validate_lawyer_ids(cls, v):
        """验证律师 ID 列表非空"""
        if not v:
            raise ValueError("至少需要指派一个律师")
        return v

    @model_validator(mode="after")
    def validate_fee(self):
        m = getattr(self, "fee_mode", None)
        fa = getattr(self, "fixed_amount", None)
        rr = getattr(self, "risk_rate", None)
        ct = getattr(self, "custom_terms", None)
        if m == FeeMode.FIXED:
            if not (fa is not None and float(fa) > 0):
                raise ValueError("固定收费需填写金额")
        elif m == FeeMode.SEMI_RISK:
            if not (fa is not None and float(fa) > 0):
                raise ValueError("半风险需填写前期金额")
            if not (rr is not None and float(rr) > 0):
                raise ValueError("半风险需填写风险比例")
        elif m == FeeMode.FULL_RISK:
            if not (rr is not None and float(rr) > 0):
                raise ValueError("全风险需填写风险比例")
        elif m == FeeMode.CUSTOM:
            if not (ct and str(ct).strip()):
                raise ValueError("自定义收费需填写条款文本")
        return self


class ContractPartyOut(ModelSchema):
    client_detail: ClientOut
    role_label: str
    
    class Meta:
        model = ContractParty
        fields = ["id", "contract", "client", "role"]

    @staticmethod
    def resolve_client_detail(obj: ContractParty) -> ClientOut:
        return obj.client

    @staticmethod
    def resolve_role_label(obj: ContractParty) -> str:
        return obj.get_role_display() if obj.role else ""


class ContractAssignmentOut(Schema):
    """合同律师指派输出 Schema"""
    id: int
    lawyer_id: int
    lawyer_name: str
    is_primary: bool
    order: int

    @staticmethod
    def from_assignment(obj) -> "ContractAssignmentOut":
        """从 ContractAssignment 对象创建 Schema"""
        return ContractAssignmentOut(
            id=obj.id,
            lawyer_id=obj.lawyer_id,
            lawyer_name=obj.lawyer.real_name if obj.lawyer and obj.lawyer.real_name else (obj.lawyer.username if obj.lawyer else ""),
            is_primary=obj.is_primary,
            order=obj.order
        )


class ContractOut(ModelSchema):
    cases: List[CaseOut]
    contract_parties: List[ContractPartyOut]
    case_type_label: str | None
    status_label: str | None
    reminders: List["ContractReminderOut"]
    payments: List["ContractPaymentOut"]
    supplementary_agreements: List["SupplementaryAgreementOut"]
    total_received: float
    total_invoiced: float
    unpaid_amount: float | None
    assignments: List[ContractAssignmentOut]
    primary_lawyer: Optional[LawyerOut]
    
    class Meta:
        model = Contract
        fields = [
            "id",
            "name",
            "case_type",
            "status",
            "start_date",
            "end_date",
            "is_archived",
            "fee_mode",
            "fixed_amount",
            "risk_rate",
            "custom_terms",
            "representation_stages",
        ]

    @staticmethod
    def resolve_cases(obj: Contract):
        return list(obj.cases.all())

    @staticmethod
    def resolve_fee_mode(obj: Contract) -> str:
        return obj.get_fee_mode_display()

    @staticmethod
    def resolve_contract_parties(obj: Contract) -> List[ContractPartyOut]:
        return list(obj.contract_parties.all())

    @staticmethod
    def resolve_representation_stages(obj: Contract) -> List[str]:
        label_map = {m.value: m.label for m in CaseStage}
        return [label_map.get(code, code) for code in (obj.representation_stages or [])]

    @staticmethod
    def resolve_case_type_label(obj: Contract) -> str | None:
        try:
            return obj.get_case_type_display()
        except Exception:
            return None

    @staticmethod
    def resolve_status_label(obj: Contract) -> str | None:
        try:
            return obj.get_status_display()
        except Exception:
            return None

    @staticmethod
    def resolve_reminders(obj: Contract):
        return list(obj.reminders.all())

    @staticmethod
    def resolve_payments(obj: Contract):
        try:
            return list(obj.payments.all())
        except Exception:
            try:
                return list(obj.contractpayment_set.all())
            except Exception:
                return []

    @staticmethod
    def resolve_total_received(obj: Contract) -> float:
        try:
            items = getattr(obj, "payments", None)
            qs = items.all() if hasattr(items, "all") else getattr(obj, "contractpayment_set", []).all() if hasattr(getattr(obj, "contractpayment_set", []), "all") else []
            return float(sum(float(p.amount or 0) for p in qs))
        except Exception:
            return 0.0

    @staticmethod
    def resolve_total_invoiced(obj: Contract) -> float:
        try:
            items = getattr(obj, "payments", None)
            qs = items.all() if hasattr(items, "all") else getattr(obj, "contractpayment_set", []).all() if hasattr(getattr(obj, "contractpayment_set", []), "all") else []
            return float(sum(float(p.invoiced_amount or 0) for p in qs))
        except Exception:
            return 0.0

    @staticmethod
    def resolve_unpaid_amount(obj: Contract) -> float | None:
        try:
            if obj.fixed_amount is None:
                return None
            val = float(obj.fixed_amount) - ContractOut.resolve_total_received(obj)
            return float(val) if val >= 0 else 0.0
        except Exception:
            return None

    @staticmethod
    def resolve_supplementary_agreements(obj: Contract):
        """解析补充协议列表"""
        return list(obj.supplementary_agreements.prefetch_related("parties__client").all())

    @staticmethod
    def resolve_assignments(obj: Contract) -> List[ContractAssignmentOut]:
        """解析律师指派列表"""
        return [ContractAssignmentOut.from_assignment(a) for a in obj.assignments.select_related("lawyer").all()]

    @staticmethod
    def resolve_primary_lawyer(obj: Contract) -> Optional[LawyerOut]:
        """解析主办律师"""
        return obj.primary_lawyer


class ContractPaymentIn(Schema):
    contract_id: int
    amount: float
    received_at: Optional[str] = None
    invoice_status: Optional[str] = InvoiceStatus.UNINVOICED
    invoiced_amount: Optional[float] = 0
    note: Optional[str] = None
    confirm: bool = False


class ContractPaymentOut(ModelSchema, SchemaMixin):
    invoice_status_label: str
    class Meta:
        model = ContractPayment
        fields = [
            "id",
            "contract",
            "amount",
            "received_at",
            "invoice_status",
            "invoiced_amount",
            "note",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_invoice_status_label(obj: ContractPayment) -> str:
        return SchemaMixin._get_display(obj, "invoice_status") or ""

    @staticmethod
    def resolve_created_at(obj: ContractPayment):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: ContractPayment):
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))


class ContractPaymentUpdate(Schema):
    amount: Optional[float] = None
    received_at: Optional[str] = None
    invoice_status: Optional[str] = None
    invoiced_amount: Optional[float] = None
    note: Optional[str] = None
    confirm: bool = False


class FinanceStatsItem(Schema):
    contract_id: int
    total_received: float
    total_invoiced: float
    unpaid_amount: float | None


class FinanceStatsOut(Schema):
    items: List[FinanceStatsItem]
    total_received_all: float
    total_invoiced_all: float


class ContractReminderIn(Schema):
    contract_id: int
    kind: str
    content: str
    due_date: str


class ContractReminderUpdate(Schema):
    contract_id: Optional[int] = None
    kind: Optional[str] = None
    content: Optional[str] = None
    due_date: Optional[str] = None


class ContractReminderOut(ModelSchema, SchemaMixin):
    kind_label: str
    class Meta:
        model = ContractReminder
        fields = [
            "id",
            "contract",
            "kind",
            "content",
            "due_date",
            "created_at",
        ]

    @staticmethod
    def resolve_kind_label(obj: ContractReminder) -> str:
        return SchemaMixin._get_display(obj, "kind") or ""

    @staticmethod
    def resolve_created_at(obj: ContractReminder):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class ContractUpdate(Schema):
    name: Optional[str] = None
    case_type: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    assigned_lawyer: Optional[int] = None
    is_archived: Optional[bool] = None
    fee_mode: Optional[str] = None
    fixed_amount: Optional[float] = None
    risk_rate: Optional[float] = None
    custom_terms: Optional[str] = None
    representation_stages: Optional[list] = None
    parties: Optional[List[ContractPartyIn]] = None  # 当事人列表（含身份）
    supplementary_agreements: Optional[List[SupplementaryAgreementInput]] = None  # 补充协议列表


# ==================== 补充协议 Schemas ====================


class SupplementaryAgreementIn(Schema):
    """补充协议创建输入 Schema"""
    contract_id: int
    name: Optional[str] = None
    party_ids: Optional[List[int]] = None  # 兼容旧接口
    parties: Optional[List[SupplementaryAgreementPartyInput]] = None  # 新接口（含身份）


class SupplementaryAgreementUpdate(Schema):
    """补充协议更新输入 Schema"""
    name: Optional[str] = None
    party_ids: Optional[List[int]] = None  # 兼容旧接口
    parties: Optional[List[SupplementaryAgreementPartyInput]] = None  # 新接口（含身份）


class SupplementaryAgreementPartyIn(Schema):
    """补充协议当事人输入"""
    client_id: int
    role: str = PartyRole.PRINCIPAL


class SupplementaryAgreementPartyOut(ModelSchema):
    """补充协议当事人输出 Schema"""
    client_name: str
    is_our_client: bool
    role_label: str

    class Meta:
        model = SupplementaryAgreementParty
        fields = ["id", "client", "role"]

    @staticmethod
    def resolve_client_name(obj) -> str:
        """解析客户名称"""
        return obj.client.name if obj.client else ""

    @staticmethod
    def resolve_is_our_client(obj) -> bool:
        """解析是否为我方客户"""
        return obj.client.is_our_client if obj.client else False

    @staticmethod
    def resolve_role_label(obj) -> str:
        """解析身份标签"""
        return obj.get_role_display() if obj.role else ""


class SupplementaryAgreementOut(ModelSchema, SchemaMixin):
    """补充协议输出 Schema"""
    parties: List[SupplementaryAgreementPartyOut]

    class Meta:
        model = SupplementaryAgreement
        fields = ["id", "contract", "name", "created_at", "updated_at"]

    @staticmethod
    def resolve_parties(obj) -> List[SupplementaryAgreementPartyOut]:
        """解析当事人列表"""
        return list(obj.parties.select_related("client").all())

    @staticmethod
    def resolve_created_at(obj):
        """解析创建时间为 ISO 格式"""
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj):
        """解析更新时间为 ISO 格式"""
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))
