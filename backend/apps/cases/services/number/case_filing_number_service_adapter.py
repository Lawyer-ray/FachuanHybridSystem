"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ICaseFilingNumberService


class CaseFilingNumberServiceAdapter(ICaseFilingNumberService):
    def __init__(self, service: Any | None = None) -> None:
        self._service = service

    @property
    def service(self) -> Any:
        if self._service is None:
            from .case_filing_number_service import CaseFilingNumberService

            self._service = CaseFilingNumberService()
        return self._service

    def generate_case_filing_number_internal(self, case_id: int, case_type: str, created_year: int) -> Any:
        return self.service.generate_case_filing_number_internal(
            case_id=case_id, case_type=case_type, created_year=created_year
        )
