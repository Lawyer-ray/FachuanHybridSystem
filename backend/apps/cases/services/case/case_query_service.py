"""Business logic services."""

from __future__ import annotations


from django.db.models import QuerySet

from apps.cases.models import Case

from .case_queryset import get_case_queryset as build_case_queryset


class CaseQueryService:
    def get_case_queryset(self) -> QuerySet[Case, Case]:
        return build_case_queryset()
