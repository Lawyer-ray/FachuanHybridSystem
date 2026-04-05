"""Business logic services."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, ClassVar, cast

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract
from apps.core.models.enums import CaseType
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import CaseDTO

from .workflows import ContractCaseCreationWorkflow, ContractCloneWorkflow, ContractFilingNumberWorkflow
from ..wiring import get_case_service, get_reminder_service

logger = logging.getLogger("apps.contracts")


class ContractAdminMutationService:
    CASE_ALLOWED_TYPES: ClassVar = {
        CaseType.CIVIL,
        CaseType.CRIMINAL,
        CaseType.ADMINISTRATIVE,
        CaseType.LABOR,
        CaseType.INTL,
    }

    def __init__(
        self,
        filing_number_service: Any | None = None,
        case_service: Any | None = None,
        reminder_service: Any | None = None,
    ) -> None:
        self._filing_number_service = filing_number_service
        self._case_service = case_service
        self._reminder_service = reminder_service
        self._clone_workflow: ContractCloneWorkflow | None = None
        self._case_creation_workflow: ContractCaseCreationWorkflow | None = None
        self._filing_number_workflow: ContractFilingNumberWorkflow | None = None

    @property
    def filing_number_service(self) -> Any:
        if self._filing_number_service is None:
            from apps.contracts.services.assignment.filing_number_service import FilingNumberService

            self._filing_number_service = FilingNumberService()
        return self._filing_number_service

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            self._case_service = get_case_service()
        return self._case_service

    @property
    def reminder_service(self) -> Any:
        if self._reminder_service is None:
            self._reminder_service = get_reminder_service()
        return self._reminder_service

    @property
    def clone_workflow(self) -> ContractCloneWorkflow:
        if self._clone_workflow is None:
            self._clone_workflow = ContractCloneWorkflow(reminder_service=self.reminder_service)
        return self._clone_workflow

    @property
    def case_creation_workflow(self) -> ContractCaseCreationWorkflow:
        if self._case_creation_workflow is None:
            self._case_creation_workflow = ContractCaseCreationWorkflow(case_service=self.case_service)
        return self._case_creation_workflow

    @property
    def filing_number_workflow(self) -> ContractFilingNumberWorkflow:
        if self._filing_number_workflow is None:
            self._filing_number_workflow = ContractFilingNumberWorkflow(
                filing_number_service=self.filing_number_service
            )
        return self._filing_number_workflow

    @transaction.atomic
    def duplicate_contract(self, contract_id: int) -> Contract:
        try:
            original = Contract.objects.get(pk=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(
                message=_("合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": _("ID为 %(id)s 的合同不存在") % {"id": contract_id}},
            ) from None

        new_contract = Contract.objects.create(
            name=_("%(name)s (副本)") % {"name": original.name},
            case_type=original.case_type,
            status=original.status,
            specified_date=original.specified_date,
            start_date=original.start_date,
            end_date=original.end_date,
            is_archived=False,
            fee_mode=original.fee_mode,
            fixed_amount=original.fixed_amount,
            risk_rate=original.risk_rate,
            custom_terms=original.custom_terms,
            representation_stages=original.representation_stages,
        )

        self.clone_workflow.clone_related_data(source_contract=original, target_contract=new_contract)

        return new_contract

    @transaction.atomic
    def create_case_from_contract(
        self,
        *,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        try:
            contract = Contract.objects.get(pk=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(
                message=_("合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": _("ID为 %(id)s 的合同不存在") % {"id": contract_id}},
            ) from None

        if contract.case_type not in self.CASE_ALLOWED_TYPES:
            raise ValidationException(
                message=_("该合同类型不支持创建案件"),
                code="INVALID_CONTRACT_TYPE",
                errors={
                    "case_type": _("合同类型 %(type)s 不支持创建案件") % {"type": contract.get_case_type_display()}
                },
            )

        from apps.core.models.enums import SimpleCaseType

        case_type_mapping = {
            CaseType.CIVIL: SimpleCaseType.CIVIL,
            CaseType.CRIMINAL: SimpleCaseType.CRIMINAL,
            CaseType.ADMINISTRATIVE: SimpleCaseType.ADMINISTRATIVE,
            CaseType.LABOR: SimpleCaseType.CIVIL,
            CaseType.INTL: SimpleCaseType.CIVIL,
        }

        case_data = {
            "name": contract.name,
            "contract_id": contract.pk,
            "case_type": case_type_mapping.get(contract.case_type, SimpleCaseType.CIVIL),
            "is_archived": False,
        }
        return self.case_creation_workflow.create_case_from_contract(
            contract=contract,
            case_data=case_data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    @transaction.atomic
    def renew_advisor_contract(self, contract_id: int) -> Contract:
        try:
            original = Contract.objects.get(pk=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(
                message=_("合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": _("ID为 %(id)s 的合同不存在") % {"id": contract_id}},
            ) from None

        if original.case_type != CaseType.ADVISOR:
            raise ValidationException(
                message=_("只有常法顾问合同才能续签"),
                code="INVALID_CONTRACT_TYPE",
                errors={
                    "case_type": _("合同类型为 %(type)s，不是常法顾问合同") % {"type": original.get_case_type_display()}
                },
            )

        new_start_date = original.start_date + relativedelta(years=1) if original.start_date else None
        new_end_date = original.end_date + relativedelta(years=1) if original.end_date else None

        new_contract = Contract.objects.create(
            name=original.name,
            case_type=original.case_type,
            status=original.status,
            specified_date=original.specified_date,
            start_date=new_start_date,
            end_date=new_end_date,
            is_archived=False,
            fee_mode=original.fee_mode,
            fixed_amount=original.fixed_amount,
            risk_rate=original.risk_rate,
            custom_terms=original.custom_terms,
            representation_stages=original.representation_stages,
        )
        self.clone_workflow.clone_related_data(
            source_contract=original,
            target_contract=new_contract,
            due_at_transform=ContractCloneWorkflow.plus_one_year_due_at,
        )

        return new_contract

    def generate_advisor_contract_name(self, principal_names: list[str], start_date: date, end_date: date) -> str:
        """生成常法顾问合同名称"""
        principals_str = "、".join(principal_names)
        start_str = start_date.strftime("%Y年%m月%d日")
        end_str = end_date.strftime("%Y年%m月%d日")
        return _("%(names)s常法顾问-%(start)s至%(end)s") % {"names": principals_str, "start": start_str, "end": end_str}

    @transaction.atomic
    def handle_contract_filing_change(self, contract_id: int, is_archived: bool) -> str | None:
        try:
            contract = Contract.objects.get(pk=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(
                message=_("合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": _("ID为 %(id)s 的合同不存在") % {"id": contract_id}},
            ) from None

        if not is_archived:
            logger.info(
                "取消合同建档,保留建档编号",
                extra={
                    "contract_id": contract_id,
                    "filing_number": contract.filing_number,
                    "action": "handle_contract_filing_change",
                },
            )
            return None

        if contract.filing_number:
            logger.info(
                "合同已有建档编号,返回现有编号",
                extra={
                    "contract_id": contract_id,
                    "filing_number": contract.filing_number,
                    "action": "handle_contract_filing_change",
                },
            )
            return cast(str | None, contract.filing_number)

        filing_number = self.filing_number_workflow.ensure_filing_number(contract=contract)

        logger.info(
            "生成并保存合同建档编号",
            extra={
                "contract_id": contract_id,
                "filing_number": filing_number,
                "action": "handle_contract_filing_change",
            },
        )

        return cast(str | None, filing_number)
