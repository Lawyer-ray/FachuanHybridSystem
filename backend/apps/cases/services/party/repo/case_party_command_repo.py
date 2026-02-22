"""Data repository layer."""

from __future__ import annotations

from apps.cases.models import Case, CaseParty


class CasePartyCommandRepo:
    def get_case(self, case_id: int) -> Case | None:
        return Case.objects.select_related("contract").filter(id=case_id).first()

    def get_party(self, party_id: int) -> CaseParty | None:
        return CaseParty.objects.select_related("case", "client").filter(id=party_id).first()

    def get_party_for_update(self, party_id: int) -> CaseParty | None:
        return CaseParty.objects.select_related("case").filter(id=party_id).first()

    def party_exists(self, *, case_id: int, client_id: int) -> bool:
        return CaseParty.objects.filter(case_id=case_id, client_id=client_id).exists()

    def create_party(self, *, case: Case, client_id: int, legal_status: str | None) -> CaseParty:
        return CaseParty.objects.create(case=case, client_id=client_id, legal_status=legal_status)
