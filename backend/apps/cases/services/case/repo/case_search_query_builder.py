"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.cases.models import Case, CaseNumber
from apps.cases.utils import normalize_case_number


class CaseSearchQueryBuilder:
    def build_case_id_query_by_case_number(self, case_number: str) -> list[Any]:
        if not case_number:
            return []

        normalized = normalize_case_number(case_number)
        if not normalized:
            return []

        return list(
            CaseNumber.objects.filter(number__icontains=normalized.rstrip("号")).values_list("case_id", flat=True)
        )

    def build_case_search_queryset(
        self, qs: QuerySet[Case, Case], query: str, status: str | None = None, limit: int = 30
    ) -> QuerySet[Case, Case]:
        if not query or not query.strip():
            return qs.none()

        query = query.strip()

        conditions = Q(name__icontains=query) | Q(parties__client__name__icontains=query)

        normalized = normalize_case_number(query)
        if normalized:
            search_term = normalized.rstrip("号")
            conditions |= Q(case_numbers__number__icontains=search_term)

        qs = qs.filter(conditions).distinct()
        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-start_date", "-id")[:limit]
