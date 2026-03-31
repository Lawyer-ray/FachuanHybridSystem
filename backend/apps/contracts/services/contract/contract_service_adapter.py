"""Business logic services."""

from __future__ import annotations

import logging
import warnings
from typing import Any

from apps.contracts.models import Contract, ContractParty
from apps.core.dto import PartyRoleDTO, SupplementaryAgreementDTO
from apps.core.exceptions import NotFoundError
from apps.core.interfaces import ContractDTO, ICaseService, LawyerDTO
from apps.core.security.access_context import AccessContext

from .assemblers.contract_details_assembler import ContractDetailsAssembler
from .assemblers.contract_dto_assembler import ContractDtoAssembler
from .contract_service import ContractService

logger = logging.getLogger("apps.contracts")


class ContractServiceAdapter:
    def __init__(
        self,
        contract_service: ContractService | None = None,
        case_service: ICaseService | None = None,
        dto_assembler: ContractDtoAssembler | None = None,
        details_assembler: ContractDetailsAssembler | None = None,
    ) -> None:
        if contract_service is not None:
            resolved_contract_service = contract_service
        else:
            if case_service is None:
                raise RuntimeError("ContractServiceAdapter 需要显式注入 case_service 或 contract_service")
            resolved_contract_service = ContractService(case_service=case_service)
        self.contract_service: ContractService = resolved_contract_service
        self.dto_assembler = dto_assembler or ContractDtoAssembler()
        self.details_assembler = details_assembler or ContractDetailsAssembler()

    def get_contract(self, contract_id: int, **kwargs: Any) -> Any:
        try:
            contract = self.contract_service.query_service.get_contract_internal(contract_id)
            return self.dto_assembler.to_dto(contract)
        except NotFoundError:
            return None

    def list_contracts(self, **kwargs: Any) -> list[Any]:
        return self.contract_service.list_contracts(**kwargs)

    def create_contract_with_cases(self, **kwargs: Any) -> Any:
        return self.contract_service.create_contract_with_cases(**kwargs)

    def update_contract_with_finance(self, **kwargs: Any) -> Any:
        return self.contract_service.update_contract_with_finance(**kwargs)

    def update_contract_lawyers(self, **kwargs: Any) -> Any:
        return self.contract_service.update_contract_lawyers(**kwargs)

    def delete_contract(self, contract_id: int) -> None:
        self.contract_service.delete_contract(contract_id)

    def get_contract_stages(self, contract_id: int) -> list[str]:
        try:
            contract = self.contract_service.query_service.get_contract_internal(contract_id)
            return contract.representation_stages or []
        except NotFoundError:
            return []

    def validate_contract_active(self, contract_id: int) -> bool:
        try:
            contract = self.contract_service.query_service.get_contract_internal(contract_id)
            return bool(contract.status == "active")
        except NotFoundError:
            return False

    def get_contracts_by_ids(self, contract_ids: list[int]) -> list[ContractDTO]:
        contracts = Contract.objects.filter(id__in=contract_ids).prefetch_related("assignments__lawyer__law_firm")
        return [self.dto_assembler.to_dto(c) for c in contracts]

    def get_contract_assigned_lawyer_id(self, contract_id: int) -> int | None:
        try:
            contract = self.contract_service.query_service.get_contract_internal(contract_id)
            primary_lawyer = getattr(contract, "primary_lawyer", None)
            return getattr(primary_lawyer, "id", None)
        except NotFoundError:
            return None

    def get_contract_lawyers(self, contract_id: int) -> list[LawyerDTO]:
        contract = self.contract_service.query_service.get_contract_internal(contract_id)
        all_lawyers = contract.all_lawyers
        return [LawyerDTO.from_model(lawyer) for lawyer in all_lawyers]

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        return self.contract_service.get_all_parties(contract_id)

    def get_contract_with_details_internal(self, contract_id: int) -> dict[str, Any] | None:
        contract = self.contract_service.query_service.get_contract_with_details_model_internal(contract_id)
        if not contract:
            return None
        return self.details_assembler.to_dict(contract)

    def get_party_roles_by_contract_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        try:
            parties = ContractParty.objects.filter(contract_id=contract_id).select_related("client")
            return [
                PartyRoleDTO(
                    id=party.id,
                    contract_id=party.contract_id,
                    client_id=party.client_id,
                    client_name=party.client.name if party.client else "",
                    role_type=party.role,
                    is_our_client=(party.role == "PRINCIPAL"),
                )
                for party in parties
            ]
        except Exception:
            logger.exception("get_party_roles_by_contract_internal_failed", extra={"contract_id": contract_id})
            raise

    def get_fee_mode_display_internal(self, fee_mode: str) -> str:
        try:
            from apps.contracts.models.contract import FeeMode

            fee_mode_choices = dict(FeeMode.choices)
            return str(fee_mode_choices.get(fee_mode, fee_mode))
        except Exception:
            logger.exception("get_fee_mode_display_internal_failed", extra={"fee_mode": fee_mode})
            return fee_mode

    def get_opposing_parties_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        all_parties = self.get_party_roles_by_contract_internal(contract_id)
        return [p for p in all_parties if p.role_type == "OPPOSING"]

    def get_principals_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        all_parties = self.get_party_roles_by_contract_internal(contract_id)
        return [p for p in all_parties if p.role_type == "PRINCIPAL"]

    def get_supplementary_agreements_internal(self, contract_id: int) -> list[SupplementaryAgreementDTO]:
        return self.contract_service.supplementary_agreement_query_service.get_supplementary_agreements_internal(
            contract_id=contract_id,
        )

    def get_contract_model_internal(self, contract_id: int) -> Any | None:
        """返回原始 Contract Model 实例（供文档生成等内部使用）。

        .. deprecated::
            此方法直接返回原始 Model 实例，破坏适配器层 DTO 封装边界。
            请使用 ``get_contract_with_details_internal`` 获取字典格式数据。
        """
        warnings.warn(
            "get_contract_model_internal 已弃用，请使用 get_contract_with_details_internal 替代",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return Contract.objects.prefetch_related("contract_parties__client", "assignments__lawyer").get(
                pk=contract_id
            )
        except Contract.DoesNotExist:
            return None

    def get_supplementary_agreement_model_internal(self, contract_id: int, agreement_id: int) -> Any | None:
        return self.contract_service.supplementary_agreement_query_service.get_supplementary_agreement_model_internal(
            contract_id=contract_id, agreement_id=agreement_id
        )

    def ensure_contract_access_ctx(self, contract_id: int, ctx: AccessContext) -> None:
        self.ensure_contract_access_ctx_internal(contract_id=contract_id, ctx=ctx)

    def ensure_contract_access_ctx_internal(self, contract_id: int, ctx: AccessContext) -> None:
        self.contract_service.access_policy.ensure_access_ctx(contract_id=contract_id, ctx=ctx)
