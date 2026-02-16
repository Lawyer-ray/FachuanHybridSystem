"""Business logic services."""

from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys


class LitigationPlaceholderContextService:
    def build_fixed_blocks(self, case_id: int, document_type: str) -> dict[str, str]:
        from apps.documents.services.placeholders.litigation import (
            ComplaintPartyService,
            ComplaintSignatureService,
            DefensePartyService,
            DefenseSignatureService,
            SupervisingAuthorityService,
        )

        court = SupervisingAuthorityService().get_supervising_authority(case_id)

        result: dict[str, str] = {LitigationPlaceholderKeys.COURT: court}

        if document_type in ["defense", "counterclaim_defense"]:
            result[LitigationPlaceholderKeys.DEFENSE_PARTY] = DefensePartyService().generate_party_info(case_id)
            result[LitigationPlaceholderKeys.DEFENSE_SIGNATURE] = DefenseSignatureService().generate_signature_info(
                case_id
            )
            return result

        result[LitigationPlaceholderKeys.COMPLAINT_PARTY] = ComplaintPartyService().generate_party_info(case_id)
        result[LitigationPlaceholderKeys.COMPLAINT_SIGNATURE] = ComplaintSignatureService().generate_signature_info(
            case_id
        )
        return result
