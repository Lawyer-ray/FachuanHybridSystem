"""Business logic services."""

from __future__ import annotations

from apps.core.interfaces import LawFirmDTO, LawyerDTO
from apps.organization.models import LawFirm, Lawyer


class LawyerDtoAssembler:
    def to_dto(self, lawyer: Lawyer) -> LawyerDTO:
        return LawyerDTO.from_model(lawyer)


class LawFirmDtoAssembler:
    def to_dto(self, lawfirm: LawFirm) -> LawFirmDTO:
        return LawFirmDTO.from_model(lawfirm)
