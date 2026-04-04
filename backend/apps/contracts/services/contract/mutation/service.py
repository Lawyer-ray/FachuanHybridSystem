"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractAssignment, ContractParty
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.contracts")

if TYPE_CHECKING:
    from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService
    from apps.core.protocols import ICaseService

    from ..domain import ContractValidator


class ContractMutationService:
    def __init__(
        self,
        *,
        validator: ContractValidator,
        lawyer_assignment_service: LawyerAssignmentService,
        case_service: ICaseService,
    ) -> None:
        self.validator = validator
        self.lawyer_assignment_service = lawyer_assignment_service
        self.case_service = case_service

    @transaction.atomic
    def create_contract(self, data: dict[str, Any]) -> Contract:
        lawyer_ids = data.pop("lawyer_ids", None)
        parties_data = data.pop("parties", None)

        non_model_fields = {"cases", "payments", "reminders", "assignments", "supplementary_agreements"}
        for field in non_model_fields:
            data.pop(field, None)

        data = {k: v for k, v in data.items() if v is not None}

        self.validator.validate_fee_mode(data)

        case_type = data.get("case_type")
        representation_stages = data.get("representation_stages", [])
        if representation_stages:
            data["representation_stages"] = self.validator.validate_stages(representation_stages, case_type)

        contract = Contract.objects.create(**data)

        if lawyer_ids:
            self.lawyer_assignment_service.set_contract_lawyers(contract.pk, lawyer_ids)

        if parties_data:
            for party in parties_data:
                client_id = party.get("client_id")
                role = party.get("role", "PRINCIPAL")
                if client_id:
                    ContractParty.objects.create(contract=contract, client_id=client_id, role=role)

        logger.info(
            "合同创建成功",
            extra={"contract_id": contract.pk, "lawyer_ids": lawyer_ids, "action": "create_contract"},
        )

        return contract

    @transaction.atomic
    def update_contract(self, contract_id: int, data: dict[str, Any]) -> Contract:
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id}) from None

        if "fee_mode" in data:
            merged_data = {**contract.__dict__, **data}
            self.validator.validate_fee_mode(merged_data)

        if "representation_stages" in data:
            case_type = data.get("case_type", contract.case_type)
            data["representation_stages"] = self.validator.validate_stages(data["representation_stages"], case_type)

        for key, value in data.items():
            setattr(contract, key, value)

        contract.save()

        logger.info("合同更新成功", extra={"contract_id": contract_id, "action": "update_contract"})

        return contract

    @transaction.atomic
    def delete_contract(self, contract_id: int) -> None:
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id}) from None

        # 不再解绑案件：Case.contract FK 已设为 CASCADE，删除合同时会级联删除案件及其日志、附件
        case_count = self.case_service.count_cases_by_contract(contract_id=contract.pk)
        contract.delete()

        logger.info(
            "合同删除成功（已级联删除关联案件及附件）",
            extra={
                "contract_id": contract_id,
                "action": "delete_contract",
                "cascaded_case_count": case_count,
            },
        )

    @transaction.atomic
    def update_contract_lawyers(self, contract_id: int, lawyer_ids: list[int]) -> list[ContractAssignment]:
        return cast(list[ContractAssignment], self.lawyer_assignment_service.set_contract_lawyers(contract_id, lawyer_ids))
