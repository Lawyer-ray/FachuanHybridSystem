"""Business logic services."""

from __future__ import annotations

from apps.core.interfaces import LawFirmDTO, LawyerDTO
from apps.organization.models import LawFirm, Lawyer


class LawyerDtoAssembler:
    def to_dto(self, lawyer: Lawyer) -> LawyerDTO:
        return LawyerDTO(
            id=lawyer.id,
            username=lawyer.username,
            real_name=lawyer.real_name,
            phone=lawyer.phone,
            is_admin=lawyer.is_admin,
            law_firm_id=lawyer.law_firm_id,
            law_firm_name=str(lawyer.law_firm.name) if lawyer.law_firm else None,
        )


class LawFirmDtoAssembler:
    def to_dto(self, lawfirm: LawFirm) -> LawFirmDTO:
        return LawFirmDTO(
            id=lawfirm.id,
            name=lawfirm.name,
            address=lawfirm.address,
            phone=lawfirm.phone,
            social_credit_code=lawfirm.social_credit_code,
        )
