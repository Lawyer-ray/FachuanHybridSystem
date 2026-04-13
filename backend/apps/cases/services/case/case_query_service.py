"""案件查询服务 - 负责所有案件读取操作。"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case
from apps.core.exceptions import NotFoundError
from apps.core.security.access_context import AccessContext as SecurityAccessContext
from apps.core.security.permissions import PermissionMixin

from .case_access_policy import CaseAccessPolicy
from .case_queryset import get_case_queryset
from .case_search_service import CaseSearchService


class CaseQueryService(PermissionMixin):
    """案件查询服务，封装所有案件读取业务逻辑。"""

    def __init__(
        self,
        search_service: CaseSearchService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self._access_policy = access_policy or CaseAccessPolicy()
        self._search_service = search_service or CaseSearchService(access_policy=self._access_policy)

    def get_case_queryset(self) -> QuerySet[Case, Case]:
        """获取带预加载的案件查询集。"""
        return get_case_queryset()

    def list_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        """获取案件列表（带权限过滤）。"""
        return self._search_service.list_cases(
            case_type=case_type,
            status=status,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def list_cases_ctx(
        self,
        *,
        ctx: SecurityAccessContext,
        case_type: str | None = None,
        status: str | None = None,
    ) -> QuerySet[Case, Case]:
        """获取案件列表（AccessContext 版本）。"""
        return self._search_service.list_cases_ctx(ctx=ctx, case_type=case_type, status=status)

    def get_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        """获取单个案件（带权限检查）。

        NotFoundError: 案件不存在
        ForbiddenError: 无权限访问
        """
        try:
            case = get_case_queryset().get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id}) from None

        self._access_policy.ensure_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
        )
        return case

    def get_case_ctx(self, *, case_id: int, ctx: SecurityAccessContext) -> Case:
        """获取单个案件（AccessContext 版本）。"""
        try:
            case = get_case_queryset().get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id}) from None

        self._access_policy.ensure_access_ctx(case_id=case.id, ctx=ctx, case=case)
        return case

    def search_cases(
        self,
        query: str,
        limit: int = 10,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[Case]:
        """综合搜索案件（案号、名称、当事人）。"""
        return self._search_service.search_cases(
            query=query,
            limit=limit,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def search_cases_ctx(self, *, ctx: SecurityAccessContext, query: str, limit: int = 10) -> list[Case]:
        """综合搜索案件（AccessContext 版本）。"""
        return self._search_service.search_cases_ctx(ctx=ctx, query=query, limit=limit)

    def search_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        """通过案号搜索案件。"""
        return self._search_service.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            exact_match=exact_match,
        )

    def search_by_case_number_ctx(
        self,
        *,
        ctx: SecurityAccessContext,
        case_number: str,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        """通过案号搜索案件（AccessContext 版本）。"""
        return self._search_service.search_by_case_number_ctx(
            ctx=ctx,
            case_number=case_number,
            exact_match=exact_match,
        )

    def check_case_access(
        self,
        case: Case,
        user: Any,
        org_access: dict[str, Any] | None,
    ) -> bool:
        """检查用户是否有权访问案件。"""
        return self._access_policy.has_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            case=case,
        )

    def check_case_access_ctx(self, *, case: Case, ctx: SecurityAccessContext) -> bool:
        """检查用户是否有权访问案件（AccessContext 版本）。"""
        return self._access_policy.has_access_ctx(case_id=case.id, ctx=ctx, case=case)
