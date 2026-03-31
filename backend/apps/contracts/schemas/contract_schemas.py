"""
Contract Schemas - Contract

合同核心 CRUD 相关的 Schema 定义.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from ninja import ModelSchema, Schema
from pydantic import field_validator, model_validator

from apps.contracts.models import Contract, FeeMode
from apps.core.models.enums import CaseStage
from apps.core.api.schemas_shared import ReminderLiteOut as ReminderOut

from .lawyer_schemas import CaseOut, LawyerOut
from .party_schemas import ContractPartyIn, ContractPartyOut
from .payment_schemas import ContractPaymentOut
from .supplementary_schemas import SupplementaryAgreementInput, SupplementaryAgreementOut

logger = logging.getLogger(__name__)


class UpdateLawyersIn(Schema):
    """更新合同律师指派输入 Schema"""

    lawyer_ids: list[int]

    @field_validator("lawyer_ids")
    @classmethod
    def validate_lawyer_ids(cls, v: Any) -> Any:
        """验证律师 ID 列表非空"""
        if not v:
            raise ValueError("至少需要指派一个律师")
        return v


class ContractIn(ModelSchema):
    specified_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    fee_mode: str | None = FeeMode.FIXED
    fixed_amount: float | None = None
    risk_rate: float | None = None
    custom_terms: str | None = None
    representation_stages: list[str] | None = None  # 代理阶段列表
    lawyer_ids: list[int]  # 律师 ID 列表,第一个为主办律师
    parties: list[ContractPartyIn] | None = None  # 当事人列表(含身份)
    supplementary_agreements: list[SupplementaryAgreementInput] | None = None  # 补充协议列表

    class Meta:
        model = Contract
        fields: ClassVar = [
            "name",
            "case_type",
            "status",
            "specified_date",
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
    def validate_lawyer_ids(cls, v: Any) -> Any:
        """验证律师 ID 列表非空"""
        if not v:
            raise ValueError("至少需要指派一个律师")
        return v

    @model_validator(mode="after")
    def validate_fee(self) -> Any:
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
        elif m == FeeMode.CUSTOM and not (ct and str(ct).strip()):
            raise ValueError("自定义收费需填写条款文本")
        return self


class ContractAssignmentOut(Schema):
    """合同律师指派输出 Schema"""

    id: int
    lawyer_id: int
    lawyer_name: str
    is_primary: bool
    order: int

    @staticmethod
    def from_assignment(obj: Any) -> ContractAssignmentOut:
        """从 ContractAssignment 对象创建 Schema"""
        return ContractAssignmentOut(
            id=obj.id,
            lawyer_id=obj.lawyer_id,
            lawyer_name=(
                obj.lawyer.real_name
                if obj.lawyer and obj.lawyer.real_name
                else (obj.lawyer.username if obj.lawyer else "")
            ),
            is_primary=obj.is_primary,
            order=obj.order,
        )


class ContractOut(ModelSchema):
    cases: list[CaseOut]
    contract_parties: list[ContractPartyOut]
    case_type_label: str | None
    status_label: str | None
    reminders: list[ReminderOut]
    payments: list[ContractPaymentOut]
    supplementary_agreements: list[SupplementaryAgreementOut]
    total_received: float
    total_invoiced: float
    unpaid_amount: float | None
    assignments: list[ContractAssignmentOut]
    primary_lawyer: LawyerOut | None
    # 新增显示字段 (Requirements: 1.4, 7.1)
    matched_document_template: str | None = None
    matched_folder_templates: str | None = None
    has_matched_templates: bool = False

    class Meta:
        model = Contract
        fields: ClassVar = [
            "id",
            "name",
            "case_type",
            "status",
            "specified_date",
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
    def resolve_cases(obj: Contract) -> list[Any]:
        dtos = getattr(obj, "case_dtos", None)
        if dtos is not None:
            return [CaseOut.from_dto(dto) for dto in dtos]
        cases = obj.cases  # type: ignore[attr-defined]
        return [CaseOut.from_model(item) for item in cases.all()]

    @staticmethod
    def resolve_fee_mode(obj: Contract) -> str:
        return obj.get_fee_mode_display()  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def resolve_contract_parties(obj: Contract) -> list[Any]:
        contract_parties = obj.contract_parties  # type: ignore[attr-defined]
        return list(contract_parties.all())

    @staticmethod
    def resolve_representation_stages(obj: Contract) -> list[str]:
        label_map = {m.value: m.label for m in CaseStage}
        return [label_map.get(code, code) for code in (obj.representation_stages or [])]  # type: ignore[misc]

    @staticmethod
    def resolve_case_type_label(obj: Contract) -> str | None:
        try:
            return obj.get_case_type_display()  # type: ignore[no-any-return, attr-defined]
        except (AttributeError, ValueError):
            return None

    @staticmethod
    def resolve_status_label(obj: Contract) -> str | None:
        try:
            return obj.get_status_display()  # type: ignore[no-any-return, attr-defined]
        except (AttributeError, ValueError):
            return None

    @staticmethod
    def resolve_reminders(obj: Contract) -> list[Any]:
        from apps.core.interfaces import ServiceLocator

        reminder_service = ServiceLocator.get_reminder_service()
        return reminder_service.export_contract_reminders_internal(contract_id=obj.id)

    @staticmethod
    def resolve_payments(obj: Contract) -> list[Any]:
        try:
            return list(obj.payments.all())  # type: ignore[attr-defined]
        except Exception:
            logger.exception("操作失败")
            return []

    @staticmethod
    def resolve_total_received(obj: Contract) -> float:
        try:
            return float(sum(float(p.amount or 0) for p in obj.payments.all()))  # type: ignore[attr-defined]
        except Exception:
            logger.exception("操作失败")
            return 0.0

    @staticmethod
    def resolve_total_invoiced(obj: Contract) -> float:
        try:
            return float(sum(float(p.invoiced_amount or 0) for p in obj.payments.all()))  # type: ignore[attr-defined]
        except Exception:
            logger.exception("操作失败")
            return 0.0

    @staticmethod
    def resolve_unpaid_amount(obj: Contract) -> float | None:
        try:
            if obj.fixed_amount is None:
                return None
            val = float(obj.fixed_amount) - ContractOut.resolve_total_received(obj)
            return float(val) if val >= 0 else 0.0
        except Exception:
            logger.exception("操作失败")

            return None

    @staticmethod
    def resolve_supplementary_agreements(obj: Contract) -> list[Any]:
        """解析补充协议列表"""
        supplementary_agreements = obj.supplementary_agreements  # type: ignore[attr-defined]
        return list(supplementary_agreements.prefetch_related("parties__client").all())

    @staticmethod
    def resolve_assignments(obj: Contract) -> list[ContractAssignmentOut]:
        """解析律师指派列表"""
        assignments = obj.assignments  # type: ignore[attr-defined]
        return [ContractAssignmentOut.from_assignment(a) for a in assignments.select_related("lawyer").all()]

    @staticmethod
    def resolve_primary_lawyer(obj: Contract) -> LawyerOut | None:
        """解析主办律师"""
        dto = getattr(obj, "primary_lawyer_dto", None)
        if dto is not None:
            return LawyerOut.from_dto(dto)
        lawyer = getattr(obj, "primary_lawyer", None)
        if lawyer is None:
            return None
        return LawyerOut.from_model(lawyer)

    @staticmethod
    def resolve_matched_document_template(obj: Contract) -> str | None:
        return getattr(obj, "_computed_matched_document_template", None)

    @staticmethod
    def resolve_matched_folder_templates(obj: Contract) -> str | None:
        return getattr(obj, "_computed_matched_folder_templates", None)

    @staticmethod
    def resolve_has_matched_templates(obj: Contract) -> bool:
        return bool(getattr(obj, "_computed_has_matched_templates", False))


class ContractUpdate(Schema):
    name: str | None = None
    case_type: str | None = None
    status: str | None = None
    specified_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    assigned_lawyer: int | None = None
    is_archived: bool | None = None
    fee_mode: str | None = None
    fixed_amount: float | None = None
    risk_rate: float | None = None
    custom_terms: str | None = None
    representation_stages: list[Any] | None = None
    parties: list[ContractPartyIn] | None = None  # 当事人列表(含身份)
    supplementary_agreements: list[SupplementaryAgreementInput] | None = None  # 补充协议列表
