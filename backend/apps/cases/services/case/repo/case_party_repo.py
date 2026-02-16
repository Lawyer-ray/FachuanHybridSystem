from collections.abc import Iterable

"""Data repository layer."""


from django.db.models import Q

from apps.cases.models import Case, CaseParty


class CasePartyRepo:
    def list_party_names_by_case(self, case_id: int) -> list[str]:
        party_names = (
            CaseParty.objects.filter(case_id=case_id).select_related("client").values_list("client__name", flat=True)
        )
        return list(party_names)

    def search_cases_by_party(self, party_names: Iterable[str], status: str | None = None) -> list[Case]:
        if not party_names:
            return []

        query = Q()
        for name in party_names:
            query |= Q(parties__client__name__icontains=name)

        qs = Case.objects.select_related("contract").prefetch_related("parties__client").filter(query).distinct()

        if status:
            qs = qs.filter(status=status)

        return list(qs)
