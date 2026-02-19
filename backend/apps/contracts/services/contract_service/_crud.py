"""合同 CRUD 操作"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.contracts.models import Contract, ContractAssignment
from apps.core.exceptions import NotFoundError, ValidationException

from ._base import ContractServiceBase

logger = logging.getLogger("apps.contracts")

__all__ = ["ContractCrudMixin"]


class ContractCrudMixin(ContractServiceBase):
    """合同 CRUD Mixin"""

    @transaction.atomic
    def create_contract(self, data: dict[str, Any]) -> Contract:
        """创建合同"""
        lawyer_ids = data.pop("lawyer_ids", None)

        self._validate_fee_mode(data)

        case_type = data.get("case_type")
        representation_stages = data.get("representation_stages", [])
        if representation_stages:
            data["representation_stages"] = self._validate_stages(representation_stages, case_type)

        contract = Contract.objects.create(**data)

        if lawyer_ids:
            self.lawyer_assignment_service.set_contract_lawyers(contract.id, lawyer_ids)

        logger.info(
            "合同创建成功",
            extra={"contract_id": contract.id, "lawyer_ids": lawyer_ids, "action": "create_contract"},
        )

        return contract

    @transaction.atomic
    def update_contract(self, contract_id: int, data: dict[str, Any]) -> Contract:
        """更新合同"""
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist as e:
            raise NotFoundError(f"合同 {contract_id} 不存在") from e

        if "fee_mode" in data:
            merged_data = {**contract.__dict__, **data}
            self._validate_fee_mode(merged_data)

        if "representation_stages" in data:
            case_type = data.get("case_type", contract.case_type)
            data["representation_stages"] = self._validate_stages(data["representation_stages"], case_type)

        for key, value in data.items():
            setattr(contract, key, value)

        contract.save()

        logger.info("合同更新成功", extra={"contract_id": contract_id, "action": "update_contract"})

        return contract

    @transaction.atomic
    def delete_contract(self, contract_id: int) -> None:
        """删除合同"""
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist as e:
            raise NotFoundError(f"合同 {contract_id} 不存在") from e

        contract.delete()

        logger.info("合同删除成功", extra={"contract_id": contract_id, "action": "delete_contract"})

    @transaction.atomic
    def update_contract_lawyers(self, contract_id: int, lawyer_ids: list[int]) -> list[ContractAssignment]:
        """更新合同律师指派"""
        if not lawyer_ids:
            raise ValidationException(
                "至少需要指派一个律师", code="EMPTY_LAWYER_IDS", errors={"lawyer_ids": "至少需要指派一个律师"}
            )

        assignments = self.lawyer_assignment_service.set_contract_lawyers(contract_id, lawyer_ids)

        logger.info(
            "合同律师指派更新成功",
            extra={"contract_id": contract_id, "lawyer_ids": lawyer_ids, "action": "update_contract_lawyers"},
        )

        return assignments

    @transaction.atomic
    def create_contract_with_cases(
        self,
        contract_data: dict[str, Any],
        cases_data: list[dict[str, Any]] | None = None,
        assigned_lawyer_ids: list[int] | None = None,
        payments_data: list[dict[str, Any]] | None = None,
        confirm_finance: bool = False,
        user: Any = None,
    ) -> Contract:
        """创建合同并关联案件"""
        if payments_data and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        supplementary_agreements_data = contract_data.pop("supplementary_agreements", None)

        lawyer_ids = contract_data.get("lawyer_ids") or assigned_lawyer_ids
        if lawyer_ids:
            contract_data["lawyer_ids"] = lawyer_ids

        contract = self.create_contract(contract_data)

        if supplementary_agreements_data:
            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=contract.id, name=sa_data.get("name"), party_ids=sa_data.get("party_ids")
                )

        if payments_data:
            self.add_payments(
                contract_id=contract.id,
                payments_data=payments_data,
                user=user,
                confirm=True,
            )

        if cases_data:
            all_lawyers = self.lawyer_assignment_service.get_all_lawyers(contract.id)
            all_lawyer_ids = [lawyer.id for lawyer in all_lawyers]

            for case_data in cases_data:
                case_create_data = {
                    "name": case_data.get("name"),
                    "contract_id": contract.id,
                    "is_archived": case_data.get("is_archived", False),
                    "case_type": case_data.get("case_type"),
                    "target_amount": case_data.get("target_amount"),
                }
                case_dto = self.case_service.create_case(case_create_data)

                for lawyer_id in all_lawyer_ids:
                    self.case_service.create_case_assignment(case_dto.id, lawyer_id)

                parties = case_data.get("parties", [])
                for party_data in parties:
                    self.case_service.create_case_party(
                        case_id=case_dto.id,
                        client_id=party_data.get("client_id"),
                        legal_status=party_data.get("legal_status"),
                    )

        logger.info(
            "合同及案件创建成功",
            extra={
                "contract_id": contract.id,
                "cases_count": len(cases_data) if cases_data else 0,
                "payments_count": len(payments_data) if payments_data else 0,
                "action": "create_contract_with_cases",
            },
        )

        return contract

    # add_payments 由 _finance.py 提供，此处声明占位供类型检查
    def add_payments(
        self,
        contract_id: int,
        payments_data: list[dict[str, Any]],
        user: Any = None,
        confirm: bool = True,
    ) -> list[Any]:
        raise NotImplementedError
