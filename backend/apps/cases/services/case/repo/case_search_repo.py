"""Data repository layer."""

from apps.cases.models import Case

from .case_search_query_builder import CaseSearchQueryBuilder


class CaseSearchRepo:
    def __init__(self, query_builder: CaseSearchQueryBuilder | None = None) -> None:
        self._query_builder = query_builder

    @property
    def query_builder(self) -> CaseSearchQueryBuilder:
        if self._query_builder is None:
            self._query_builder = CaseSearchQueryBuilder()
        return self._query_builder

    def search_cases_by_case_number(self, case_number: str) -> list[Case]:
        case_ids = self.query_builder.build_case_id_query_by_case_number(case_number)
        if not case_ids:
            return []

        return list(Case.objects.select_related("contract").filter(id__in=case_ids))

    def search_cases(self, query: str, status: str | None = None, limit: int = 30) -> list[Case]:
        base_qs = Case.objects.select_related("contract").prefetch_related("parties__client")
        qs = self.query_builder.build_case_search_queryset(base_qs, query=query, status=status, limit=limit)
        return list(qs)
