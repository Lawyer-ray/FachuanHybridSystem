"""Business logic services."""

from typing import Any

from django.db.models import Q, QuerySet

from apps.cases.models import Case, CaseNumber
from apps.cases.utils import normalize_case_number as normalize_case_number_util
from apps.core.security.access_context import AccessContext

from .case_access_policy import CaseAccessPolicy
from .case_queryset import get_case_queryset


def normalize_case_number(number: str) -> str:
    return normalize_case_number_util(number, ensure_hao=True)


class CaseSearchService:
    def __init__(self, access_policy: CaseAccessPolicy | None = None) -> None:
        self.access_policy = access_policy or CaseAccessPolicy()

    def search_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        normalized = normalize_case_number(case_number)
        if not normalized:
            return Case.objects.none()

        if exact_match:
            case_ids = CaseNumber.objects.filter(number=normalized).values_list("case_id", flat=True)
        else:
            search_term = normalized.rstrip("号")
            case_ids = CaseNumber.objects.filter(number__icontains=search_term).values_list("case_id", flat=True)

        qs = get_case_queryset().filter(id__in=case_ids)
        return self.access_policy.filter_queryset(
            qs, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def search_by_case_number_ctx(
        self, *, ctx: AccessContext, case_number: str, exact_match: bool = False
    ) -> QuerySet[Case, Case]:
        return self.search_by_case_number(
            case_number=case_number,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            exact_match=exact_match,
        )

    def search_cases(
        self,
        query: str,
        limit: int = 10,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[Case]:
        if not query or not query.strip():
            return []

        query_value = query.strip()
        qs = get_case_queryset()

        search_conditions = Q()

        normalized_query = normalize_case_number(query_value)
        if normalized_query:
            search_term = normalized_query.rstrip("号")
            case_ids_by_number = CaseNumber.objects.filter(number__icontains=search_term).values_list(
                "case_id", flat=True
            )
            search_conditions |= Q(id__in=case_ids_by_number)

        search_conditions |= Q(name__icontains=query_value)
        search_conditions |= Q(parties__client__name__icontains=query_value)

        qs = qs.filter(search_conditions).distinct()

        qs = self.access_policy.filter_queryset(qs, user=user, org_access=org_access, perm_open_access=perm_open_access)
        return list(qs[:limit])

    def search_cases_ctx(self, *, ctx: AccessContext, query: str, limit: int = 10) -> list[Case]:
        return self.search_cases(
            query=query,
            limit=limit,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def list_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        qs = get_case_queryset().order_by("-id")

        if case_type:
            qs = qs.filter(contract__case_type=case_type)
        if status:
            qs = qs.filter(contract__status=status)

        return self.access_policy.filter_queryset(
            qs, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def list_cases_ctx(
        self, *, ctx: AccessContext, case_type: str | None = None, status: str | None = None
    ) -> QuerySet[Case, Case]:
        return self.list_cases(
            case_type=case_type,
            status=status,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
