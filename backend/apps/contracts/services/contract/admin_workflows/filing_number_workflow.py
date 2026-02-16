"""Business workflow orchestration."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.contracts.models import Contract


class ContractFilingNumberWorkflow:
    def __init__(self, *, filing_number_service: Any) -> None:
        self.filing_number_service = filing_number_service

    def ensure_filing_number(self, *, contract: Contract) -> Any:
        if contract.filing_number:
            return contract.filing_number

        if contract.specified_date:
            created_year = contract.specified_date.year
        else:
            created_year = timezone.localdate().year

        filing_number = self.filing_number_service.generate_contract_filing_number(
            contract_id=contract.id,
            case_type=contract.case_type,
            created_year=created_year,
        )

        contract.filing_number = filing_number
        contract.save(update_fields=["filing_number"])

        return filing_number
