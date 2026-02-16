"""Business logic services."""

from typing import Any

from apps.core.dtos import CaseDTO


class CaseDtoAssembler:
    def to_dto(self, case: Any, case_number: str | None = None) -> CaseDTO:
        dto = CaseDTO.from_model(case)
        dto.case_number = case_number
        return dto

    def to_dtos(self, cases: list[Any], case_number_map: dict[int, str | None] | None = None) -> list[CaseDTO]:
        case_number_map = case_number_map or {}
        return [self.to_dto(case, case_number_map.get(case.id)) for case in cases]
