"""Business logic services."""

from __future__ import annotations

from apps.contracts.models import Contract


class ContractListAssembler:
    def enrich(self, contracts: list[Contract]) -> None:
        if not contracts:
            return
        self._attach_template_info(contracts)
        self._attach_dtos(contracts)

    def _attach_template_info(self, contracts: list[Contract]) -> None:
        from apps.contracts.services.contract.contract_display_service import ContractDisplayService

        service = ContractDisplayService()
        info_map = service.batch_get_template_info(contracts)
        for contract in contracts:
            info = info_map.get(contract.id, {})
            contract._computed_matched_document_template = info.get("document_template") # type: ignore
            contract._computed_matched_folder_templates = info.get("folder_template") # type: ignore
            contract._computed_has_matched_templates = bool(info.get("has_templates", False)) # type: ignore

    def _attach_dtos(self, contracts: list[Contract]) -> None:
        from apps.core.dtos import CaseDTO, LawyerDTO

        for contract in contracts:
            cases = getattr(contract, "cases", None)
            if cases is not None and hasattr(cases, "all"):
                contract.case_dtos = [CaseDTO.from_model(c) for c in cases.all()] # type: ignore
            primary_lawyer = getattr(contract, "primary_lawyer", None)
            if primary_lawyer is not None:
                contract.primary_lawyer_dto = LawyerDTO.from_model(primary_lawyer) # type: ignore
