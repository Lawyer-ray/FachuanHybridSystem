"""Business logic services."""

from typing import cast

from apps.core.interfaces import LawFirmDTO, LawyerDTO
from apps.organization.models import LawFirm, Lawyer


class LawyerDtoAssembler:
    def to_dto(self, lawyer: Lawyer) -> LawyerDTO:
        return LawyerDTO(
            id=cast(int, lawyer.pk),
            username=lawyer.username,
            real_name=lawyer.real_name,
            phone=lawyer.phone,
            is_admin=lawyer.is_admin,
            law_firm_id=cast(int, getattr(lawyer, "law_firm_id", 0)),
            law_firm_name=str(lawyer.law_firm.name) if lawyer.law_firm else None,
        )


class LawFirmDtoAssembler:
    def to_dto(self, lawfirm: LawFirm) -> LawFirmDTO:
        return LawFirmDTO(
            id=cast(int, lawfirm.pk),
            name=lawfirm.name,
            address=lawfirm.address,
            phone=lawfirm.phone,
            social_credit_code=lawfirm.social_credit_code,
        )
