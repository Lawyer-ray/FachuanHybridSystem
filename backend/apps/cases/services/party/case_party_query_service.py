"""Business logic services."""

import logging
from typing import Any

from django.db.models import QuerySet

from apps.cases.models import CaseParty
from apps.core.business_config import business_config
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.cases")


class CasePartyQueryService:
    def base_queryset(self) -> QuerySet[CaseParty, CaseParty]:
        return CaseParty.objects.select_related("case", "client").order_by("-id")

    def list_parties(self, *, case_id: int | None = None) -> QuerySet[CaseParty, CaseParty]:
        qs = self.base_queryset()
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def get_party(self, *, party_id: int) -> CaseParty:
        party = self.base_queryset().filter(id=party_id).first()
        if not party:
            raise NotFoundError(
                message="当事人不存在", code="PARTY_NOT_FOUND", errors={"party_id": f"ID 为 {party_id} 的当事人不存在"}
            )
        return party

    def get_available_legal_statuses(self, *, case_id: int) -> list[dict[str, Any]]:
        from apps.cases.models import Case

        case = Case.objects.filter(id=case_id).only("id", "case_type").first()
        if not case:
            raise NotFoundError(
                message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )

        existing_statuses: list[str] = list(
            CaseParty.objects.filter(case_id=case_id)
            .exclude(legal_status__isnull=True)
            .exclude(legal_status="")
            .values_list("legal_status", flat=True)
        )

        compatible_statuses = business_config.get_compatible_legal_statuses(
            existing_statuses=existing_statuses,
            case_type=case.case_type,
        )
        return [{"value": value, "label": label} for value, label in compatible_statuses]
