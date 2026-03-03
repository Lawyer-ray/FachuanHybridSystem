"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Q, QuerySet
from django.utils.functional import Promise

from apps.core.exceptions import ForbiddenError
from apps.core.security import OrgAllowedLawyersMixin

from .repo import CaseAssignmentRepo

if TYPE_CHECKING:
    from apps.core.security.access_context import AccessContext


class CaseAccessPolicy(OrgAllowedLawyersMixin):
    def __init__(self, case_assignment_repo: CaseAssignmentRepo | None = None) -> None:
        self._case_assignment_repo = case_assignment_repo

    @property
    def case_assignment_repo(self) -> CaseAssignmentRepo:
        if self._case_assignment_repo is None:
            self._case_assignment_repo = CaseAssignmentRepo()
        return self._case_assignment_repo

    def _get_extra_cases(self, org_access: dict[str, Any] | None) -> set[int]:
        if not org_access:
            return set()
        extra = org_access.get("extra_cases", set())
        if isinstance(extra, set):
            return extra
        return set(extra)

    def has_access(
        self,
        case_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
        case: Any | None = None,
    ) -> bool:
        if perm_open_access:
            return True
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_admin", False):
            return True

        extra_cases = self._get_extra_cases(org_access)
        if case_id in extra_cases:
            return True

        allowed_lawyers = self.get_allowed_lawyer_ids(user, org_access)
        if not allowed_lawyers:
            return False

        if case is not None:
            return cast(bool, case.assignments.filter(Q(lawyer_id__in=list(allowed_lawyers))).exists())

        return self.case_assignment_repo.has_case_access(case_id, list(allowed_lawyers))

    def ensure_access(
        self,
        *,
        case_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
        case: Any | None = None,
        message: str | Promise = "无权限访问此案件",
    ) -> None:
        if self.has_access(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
        ):
            return
        raise ForbiddenError(message)

    def can_access(self, user: Any | None) -> bool:
        """检查用户是否可以访问"""
        return bool(user and getattr(user, "is_authenticated", False))

    def filter_queryset(
        self,
        qs: QuerySet[Any, Any],
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
    ) -> QuerySet[Any, Any]:
        if perm_open_access:
            return qs
        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()
        if getattr(user, "is_admin", False):
            return qs

        extra_cases = self._get_extra_cases(org_access)
        allowed_lawyers = self.get_allowed_lawyer_ids(user, org_access)
        if not extra_cases and not allowed_lawyers:
            return qs.none()

        return qs.filter(Q(assignments__lawyer_id__in=list(allowed_lawyers)) | Q(id__in=list(extra_cases))).distinct()

    def has_access_ctx(self, *, case_id: int, ctx: AccessContext, case: Any | None = None) -> bool:
        return self.has_access(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            case=case,
        )

    def ensure_access_ctx(
        self, *, case_id: int, ctx: AccessContext, case: Any | None = None, message: str | Promise = "无权限访问此案件"
    ) -> None:
        return self.ensure_access(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            case=case,
            message=message,
        )

    def filter_queryset_ctx(self, qs: QuerySet[Any, Any], ctx: AccessContext) -> QuerySet[Any, Any]:
        return self.filter_queryset(
            qs=qs, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access
        )
