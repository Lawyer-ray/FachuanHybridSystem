"""合同服务适配器 — 将 Model 转换为 DTO，实现 IContractService Protocol"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any, cast

from apps.contracts.models import Contract
from apps.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from apps.contracts.dtos import ContractDTO
    from apps.core.dtos import LawyerDTO
    from apps.core.interfaces import ICaseService
    from .contract_service import ContractService

logger = logging.getLogger("apps.contracts")


class ContractServiceAdapter:
    """
    合同服务适配器
    实现 IContractService Protocol，将 Model 转换为 DTO
    """

    def __init__(
        self,
        contract_service: ContractService | None = None,
        case_service: ICaseService | None = None,
    ):
        if contract_service is not None:
            self.contract_service = contract_service
        else:
            from .contract_service import ContractService as _ContractService
            self.contract_service = _ContractService(case_service=case_service)

    def _to_dto(self, contract: Contract) -> ContractDTO:
        from apps.core.interfaces import ContractDTO
        return ContractDTO.from_model(contract)

    def get_contract(self, contract_id: int) -> ContractDTO | None:
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return self._to_dto(contract)
        except NotFoundError:
            return None

    def get_contract_stages(self, contract_id: int) -> list[str]:
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return cast(list[str], contract.representation_stages or [])
        except NotFoundError:
            return []

    def validate_contract_active(self, contract_id: int) -> bool:
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return bool(contract.status == "active")
        except NotFoundError:
            return False

    def get_contracts_by_ids(self, contract_ids: list[int]) -> list[ContractDTO]:
        contracts = Contract.objects.filter(id__in=contract_ids).prefetch_related("assignments__lawyer__law_firm")
        return [self._to_dto(c) for c in contracts]

    def get_contract_assigned_lawyer_id(self, contract_id: int) -> int | None:
        from .assignment.contract_assignment_query_service import ContractAssignmentQueryService

        query_service = ContractAssignmentQueryService()
        assignment = query_service.get_primary_lawyer(contract_id)
        if assignment is not None:
            return int(assignment.lawyer_id)
        return None

    def get_contract_lawyers(self, contract_id: int) -> list[LawyerDTO]:
        from apps.core.interfaces import LawyerDTO
        from .assignment.contract_assignment_query_service import ContractAssignmentQueryService

        query_service = ContractAssignmentQueryService()
        assignments = query_service.get_all_lawyers(contract_id)
        return [LawyerDTO.from_model(a.lawyer) for a in assignments]

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        """获取合同及其补充协议的所有当事人（去重）"""
        contract = self.contract_service._get_contract_internal(contract_id)

        parties_dict: dict[int, dict[str, Any]] = {}

        for party in contract.contract_parties.select_related("client").all():
            client = party.client
            if client.id not in parties_dict:
                parties_dict[client.id] = {
                    "id": client.id,
                    "name": client.name,
                    "source": "contract",
                }

        for sa in contract.supplementary_agreements.prefetch_related("parties__client").all():
            for sa_party in sa.parties.all():
                client = sa_party.client
                if client.id not in parties_dict:
                    parties_dict[client.id] = {
                        "id": client.id,
                        "name": client.name,
                        "source": "supplementary",
                    }

        return list(parties_dict.values())

    def get_contract_model_internal(self, contract_id: int) -> Any | None:
        """返回原始 Contract Model 实例（供文档生成等内部使用）。

        .. deprecated::
            此方法直接返回原始 Model 实例，破坏适配器层 DTO 封装边界。
            请使用 ``get_contract_with_details_internal`` 获取字典格式数据。
        """
        warnings.warn(
            "get_contract_model_internal 已弃用，请使用 "
            "get_contract_with_details_internal 替代",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return Contract.objects.prefetch_related(
                "contract_parties__client", "assignments__lawyer"
            ).get(pk=contract_id)
        except Contract.DoesNotExist:
            return None

    def get_contract_with_details_internal(self, contract_id: int) -> dict[str, Any] | None:
        """返回合同详情字典（供文档生成等内部使用）。"""
        contract = self.get_contract_model_internal(contract_id)
        if not contract:
            return None

        contract_parties = []
        for party in contract.contract_parties.all():
            client = party.client
            contract_parties.append(
                {
                    "id": party.id,
                    "client_id": client.id,
                    "client_name": client.name,
                    "id_number": getattr(client, "id_number", None),
                    "address": getattr(client, "address", None),
                    "phone": getattr(client, "phone", None),
                    "role": party.role,
                }
            )

        assignments = []
        for assignment in contract.assignments.all():
            lawyer = assignment.lawyer
            assignments.append(
                {
                    "id": assignment.id,
                    "lawyer_id": lawyer.id,
                    "lawyer_name": getattr(lawyer, "real_name", None) or str(lawyer),
                    "lawyer_phone": getattr(lawyer, "phone", None),
                    "lawyer_license_no": getattr(lawyer, "license_no", None),
                    "is_primary": assignment.is_primary,
                    "order": getattr(assignment, "order", 0),
                }
            )

        return {
            "id": contract.id,
            "name": contract.name,
            "case_type": contract.case_type,
            "case_type_display": contract.get_case_type_display(),  # type: ignore[attr-defined]
            "status": contract.status,
            "status_display": contract.get_status_display(),  # type: ignore[attr-defined]
            "fee_mode": contract.fee_mode,
            "fee_mode_display": contract.get_fee_mode_display() if hasattr(contract, "get_fee_mode_display") else "",  # type: ignore[attr-defined]
            "fixed_amount": contract.fixed_amount,
            "risk_rate": contract.risk_rate,
            "custom_terms": getattr(contract, "custom_terms", None),
            "representation_stages": contract.representation_stages or [],
            "specified_date": str(contract.specified_date) if getattr(contract, "specified_date", None) else None,
            "start_date": str(contract.start_date) if getattr(contract, "start_date", None) else None,
            "end_date": str(contract.end_date) if getattr(contract, "end_date", None) else None,
            "is_archived": getattr(contract, "is_archived", False),
            "contract_parties": contract_parties,
            "assignments": assignments,
        }
