"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.cases.models import Case
from apps.core.exceptions import NotFoundError
from apps.core.security.access_context import AccessContext

from .case_access_policy import CaseAccessPolicy
from .case_query_service import CaseQueryService
from .case_search_service import CaseSearchService


class CaseQueryFacade:
    def __init__(
        self,
        search_service: CaseSearchService | None = None,
        query_service: CaseQueryService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self.access_policy = access_policy or CaseAccessPolicy()
        self.search_service = search_service or CaseSearchService(access_policy=self.access_policy)
        self.query_service = query_service or CaseQueryService()

    def get_case_queryset(self) -> QuerySet[Case, Case]:
        return self.query_service.get_case_queryset()

    def search_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        return self.search_service.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            exact_match=exact_match,
        )

    def search_by_case_number_ctx(
        self,
        *,
        ctx: AccessContext,
        case_number: str,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        return self.search_service.search_by_case_number_ctx(
            ctx=ctx,
            case_number=case_number,
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
        return self.search_service.search_cases(
            query=query,
            limit=limit,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def search_cases_ctx(self, *, ctx: AccessContext, query: str, limit: int = 10) -> list[Case]:
        return self.search_service.search_cases_ctx(
            ctx=ctx,
            query=query,
            limit=limit,
        )

    def list_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        return self.search_service.list_cases(
            case_type=case_type,
            status=status,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def list_cases_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
    ) -> QuerySet[Case, Case]:
        return self.search_service.list_cases_ctx(
            ctx=ctx,
            case_type=case_type,
            status=status,
        )

    def get_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        try:
            case = self.get_case_queryset().get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None

        self.access_policy.ensure_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
            message="无权限访问此案件",
        )

        return case

    def get_case_ctx(self, *, case_id: int, ctx: AccessContext) -> Any:
        try:
            case = self.get_case_queryset().get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None

        self.access_policy.ensure_access_ctx(case_id=case.id, ctx=ctx, case=case, message="无权限访问此案件")

        return case
