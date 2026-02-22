"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.cases.models import CaseParty

if TYPE_CHECKING:
    from apps.core.dtos import CasePartyDTO

logger = logging.getLogger("apps.cases")


class CasePartyInternalQueryService:
    def get_case_parties_by_legal_status_internal(self, case_id: int, legal_status: str) -> list[str]:
        try:
            party_names = (
                CaseParty.objects.filter(case_id=case_id, legal_status=legal_status)
                .select_related("client")
                .values_list("client__name", flat=True)
            )
            return [name for name in party_names if name]
        except Exception:
            logger.exception(
                "get_case_parties_by_legal_status_internal_failed",
                extra={"case_id": case_id, "legal_status": legal_status},
            )
            raise

    def get_case_parties_internal(self, case_id: int, legal_status: str | None = None) -> list[CasePartyDTO]:
        try:
            from apps.core.dtos import CasePartyDTO

            qs = CaseParty.objects.select_related("client").filter(case_id=case_id)
            if legal_status:
                qs = qs.filter(legal_status=legal_status)

            result: list[CasePartyDTO] = []
            for party in qs:
                client = party.client
                result.append(
                    CasePartyDTO(
                        id=party.id,
                        case_id=party.case_id,
                        client_id=party.client_id,
                        client_name=client.name if client else "",
                        client_type=client.client_type if client else "natural",
                        legal_status=party.legal_status or "",
                        id_number=client.id_number if client else None,
                        address=client.address if client else None,
                        phone=client.phone if client else None,
                        legal_representative=getattr(client, "legal_representative", None),
                        is_our_client=client.is_our_client if client else False,
                    )
                )
            return result
        except Exception:
            logger.exception(
                "get_case_parties_internal_failed", extra={"case_id": case_id, "legal_status": legal_status}
            )
            raise
