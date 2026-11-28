"""Business logic services."""

from __future__ import annotations

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
        slim: bool = False,
    ) -> QuerySet[Case, Case]:
        normalized = normalize_case_number(case_number)
        if not normalized:
            return Case.objects.none()

        if exact_match:
            case_ids = CaseNumber.objects.filter(number=normalized).values_list("case_id", flat=True)
        else:
            search_term = normalized.rstrip("号")
            case_ids = CaseNumber.objects.filter(number__icontains=search_term).values_list("case_id", flat=True)

        qs = get_case_queryset(slim=slim).filter(id__in=case_ids)
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
        offset: int = 0,
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
        bounded_offset = max(0, offset)
        return list(qs[bounded_offset : bounded_offset + limit])

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
        contract_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        slim: bool = False,
    ) -> QuerySet[Case, Case]:
        qs = get_case_queryset(slim=slim).order_by("-id")

        # status/case_type 是 Case 自身字段（与 Contract 同名但语义独立），
        # 按 contract__ 过滤会丢掉无合同关联的案件，这里直接过滤 Case 字段
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)

        return self.access_policy.filter_queryset(
            qs, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def count_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        contract_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> int:
        """与 list_cases **同一套过滤 + 可见性口径**的总数（与 limit/offset 无关）。

        专供端点回 X-Total-Count：口径必须和列表本身逐条对齐（同一个 list_cases
        再 .count()），否则「列表 3 条、总数 4」这种对不上的数比没有总数更坏。
        这里用不到预取，故不传 slim（prefetch 不影响 count 的 SQL）。
        """
        return self.list_cases(
            case_type=case_type,
            status=status,
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ).count()

    def count_cases_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> int:
        """与 search_by_case_number 同口径的总数（端点走案号分支时用它）。"""
        return self.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ).count()

    def list_cases_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        contract_id: int | None = None,
    ) -> QuerySet[Case, Case]:
        return self.list_cases(
            case_type=case_type,
            status=status,
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
