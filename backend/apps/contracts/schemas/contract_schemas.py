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
from apps.core.api.schemas_shared import ReminderLiteOut as ReminderOut
from apps.core.models.enums import CaseStage

from .lawyer_schemas import CaseOut, LawyerOut
from .party_schemas import ContractPartyIn, ContractPartyOut
from .payment_schemas import ContractPaymentOut
from .supplementary_schemas import SupplementaryAgreementInput, SupplementaryAgreementOut


class FinalizedMaterialOut(Schema):
    """归档材料输出 Schema"""

    id: int
    category: str
    category_label: str = ""
    filename: str = ""
    original_filename: str
    file_url: str = ""
    file_size: int | None = None
    source: str = ""
    source_label: str = ""
    order: int = 0
    archive_item_code: str = ""
    remark: str = ""
    uploaded_at: str | None = None
    created_at: str | None = None

    @staticmethod
    def resolve_category_label(obj: Any) -> str:
        try:
            return str(obj.get_category_display())
        except (AttributeError, ValueError):
            return obj.category or ""

    @staticmethod
    def resolve_filename(obj: Any) -> str:
        from pathlib import Path

        return Path(obj.file_path).name if obj.file_path else ""

    @staticmethod
    def resolve_file_url(obj: Any) -> str:
        from django.conf import settings

        if obj.file_path:
            media_url = getattr(settings, "MEDIA_URL", "/media/")
            return f"{media_url}{obj.file_path}"
        return ""

    @staticmethod
    def resolve_uploaded_at(obj: Any) -> str | None:
        if obj.uploaded_at:
            return str(obj.uploaded_at.isoformat())
        return None

    @staticmethod
    def resolve_created_at(obj: Any) -> str | None:
        if hasattr(obj, "created_at") and obj.created_at:
            return str(obj.created_at.isoformat())
        return None


class ClientPaymentRecordOut(Schema):
    """客户回款记录输出 Schema"""

    id: int
    contract: int
    amount: float
    image_path: str | None = None
    note: str | None = None
    created_at: str | None = None

    @staticmethod
    def resolve_contract(obj: Any) -> int:
        return int(obj.contract_id)

    @staticmethod
    def resolve_amount(obj: Any) -> float:
        return float(obj.amount or 0)

    @staticmethod
    def resolve_created_at(obj: Any) -> str | None:
        if obj.created_at:
            return str(obj.created_at.isoformat())
        return None


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
            "is_filed",
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
    # 归档与客户回款
    client_payment_records: list[ClientPaymentRecordOut] = []
    finalized_materials: list[FinalizedMaterialOut] = []
    can_archive: bool = False

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
            "is_filed",
            "filing_number",
            "fee_mode",
            "fixed_amount",
            "risk_rate",
            "custom_terms",
            "representation_stages",
            "law_firm_oa_url",
            "law_firm_oa_case_number",
        ]

    @staticmethod
    def resolve_cases(obj: Contract) -> list[Any]:
        dtos = getattr(obj, "case_dtos", None)
        if dtos is not None:
            return [CaseOut.from_dto(dto) for dto in dtos]
        cases = obj.cases
        return [CaseOut.from_model(item) for item in cases.all()]

    @staticmethod
    def resolve_fee_mode(obj: Contract) -> str:
        return str(obj.get_fee_mode_display())

    @staticmethod
    def resolve_contract_parties(obj: Contract) -> list[Any]:
        contract_parties = obj.contract_parties
        return list(contract_parties.all())

    @staticmethod
    def resolve_representation_stages(obj: Contract) -> list[str]:
        label_map = {m.value: m.label for m in CaseStage}
        return [label_map.get(code, code) for code in (obj.representation_stages or [])]

    @staticmethod
    def resolve_case_type_label(obj: Contract) -> str | None:
        try:
            return str(obj.get_case_type_display())
        except (AttributeError, ValueError):
            return None

    @staticmethod
    def resolve_status_label(obj: Contract) -> str | None:
        try:
            return str(obj.get_status_display())
        except (AttributeError, ValueError):
            return None

    @staticmethod
    def resolve_reminders(obj: Contract) -> list[Any]:
        from apps.core.interfaces import ServiceLocator

        reminder_service = ServiceLocator.get_reminder_service()
        return list(reminder_service.export_contract_reminders_internal(contract_id=obj.id))

    @staticmethod
    def resolve_payments(obj: Contract) -> list[Any]:
        try:
            return list(obj.payments.all())
        except Exception:
            logger.exception("操作失败")
            return []

    @staticmethod
    def resolve_total_received(obj: Contract) -> float:
        try:
            return float(sum(float(p.amount or 0) for p in obj.payments.all()))
        except (TypeError, ValueError):
            logger.exception("操作失败")
            return 0.0

    @staticmethod
    def resolve_total_invoiced(obj: Contract) -> float:
        try:
            return float(sum(float(p.invoiced_amount or 0) for p in obj.payments.all()))
        except (TypeError, ValueError):
            logger.exception("操作失败")
            return 0.0

    @staticmethod
    def resolve_unpaid_amount(obj: Contract) -> float | None:
        try:
            if obj.fixed_amount is None:
                return None
            val = float(obj.fixed_amount) - ContractOut.resolve_total_received(obj)
            return float(val) if val >= 0 else 0.0
        except (TypeError, ValueError):
            logger.exception("操作失败")

            return None

    @staticmethod
    def resolve_supplementary_agreements(obj: Contract) -> list[Any]:
        """解析补充协议列表（上游已预取 parties__client）"""
        return list(obj.supplementary_agreements.all())

    @staticmethod
    def resolve_assignments(obj: Contract) -> list[ContractAssignmentOut]:
        """解析律师指派列表（上游已预取 lawyer）"""
        return [ContractAssignmentOut.from_assignment(a) for a in obj.assignments.all()]

    @staticmethod
    def resolve_primary_lawyer(obj: Contract) -> LawyerOut | None:
        """解析主办律师（使用预取数据避免额外查询）"""
        dto = getattr(obj, "primary_lawyer_dto", None)
        if dto is not None:
            return LawyerOut.from_dto(dto)
        # 使用预取的 assignments 数据，避免额外查询
        primary = None
        fallback = None
        for assignment in obj.assignments.all():
            if assignment.is_primary:
                primary = assignment
                break
            if fallback is None or (assignment.order, assignment.id) < (fallback.order, fallback.id):
                fallback = assignment
        chosen = primary or fallback
        if chosen is None or chosen.lawyer is None:
            return None
        return LawyerOut.from_model(chosen.lawyer)

    @staticmethod
    def resolve_matched_document_template(obj: Contract) -> str | None:
        value = getattr(obj, "_computed_matched_document_template", None)
        return None if value is None else str(value)

    @staticmethod
    def resolve_matched_folder_templates(obj: Contract) -> str | None:
        value = getattr(obj, "_computed_matched_folder_templates", None)
        return None if value is None else str(value)

    @staticmethod
    def resolve_has_matched_templates(obj: Contract) -> bool:
        return bool(getattr(obj, "_computed_has_matched_templates", False))

    @staticmethod
    def resolve_client_payment_records(obj: Contract) -> list[Any]:
        try:
            return list(obj.client_payment_records.all())
        except Exception:
            logger.exception("操作失败")
            return []

    @staticmethod
    def resolve_finalized_materials(obj: Contract) -> list[Any]:
        try:
            return list(obj.finalized_materials.all())
        except Exception:
            logger.exception("操作失败")
            return []

    @staticmethod
    def resolve_can_archive(obj: Contract) -> bool:
        try:
            from apps.contracts.models.finalized_material import MaterialCategory

            required_categories = {
                MaterialCategory.CONTRACT_ORIGINAL,
                MaterialCategory.ARCHIVE_DOCUMENT,
                MaterialCategory.AUTHORIZATION_MATERIAL,
            }
            # 使用预取的 finalized_materials 数据，避免额外查询
            existing = {m.category for m in obj.finalized_materials.all() if m.category in required_categories}
            return required_categories.issubset(existing)
        except Exception:
            logger.exception("操作失败")
            return False


class ContractUpdate(Schema):
    name: str | None = None
    case_type: str | None = None
    status: str | None = None
    specified_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    assigned_lawyer: int | None = None
    is_filed: bool | None = None
    fee_mode: str | None = None
    fixed_amount: float | None = None
    risk_rate: float | None = None
    custom_terms: str | None = None
    representation_stages: list[Any] | None = None
    parties: list[ContractPartyIn] | None = None  # 当事人列表(含身份)
    supplementary_agreements: list[SupplementaryAgreementInput] | None = None  # 补充协议列表


class ContractPaginatedOut(Schema):
    """合同分页输出 Schema"""

    items: list[ContractOut]
    total: int
    page: int
    page_size: int
    total_pages: int
