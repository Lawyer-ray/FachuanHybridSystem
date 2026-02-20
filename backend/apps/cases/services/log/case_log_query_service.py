"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

from typing import Any, cast

from django.db.models import QuerySet

from apps.cases.models import Case, CaseLog
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.exceptions import NotFoundError

from .case_log_query_repo import CaseLogQueryRepo


class CaseLogQueryService:
    def __init__(
        self,
        access_policy: CaseAccessPolicy | None = None,
        query_repo: CaseLogQueryRepo | None = None,
    ) -> None:
        self.access_policy = access_policy or CaseAccessPolicy()
        self.query_repo = query_repo or CaseLogQueryRepo()

    def list_logs(
        self,
        *,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        qs = CaseLog.objects.all().order_by("-created_at").select_related("actor").prefetch_related("attachments")

        if case_id:
            qs = qs.filter(case_id=case_id)

        if perm_open_access:
            return qs

        allowed_case_ids_qs = self.access_policy.filter_queryset(
            Case.objects.all(),
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ).values_list("id", flat=True)
        return self.query_repo.filter_by_allowed_case_ids(qs, allowed_case_ids_qs)

    def get_log(
        self,
        *,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseLog:
        log = self.get_log_internal(log_id=log_id)

        if perm_open_access:
            return cast(CaseLog, log)

        self.access_policy.ensure_access(
            case_id=log.case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=log.case,
            message=_("无权限访问此日志"),
        )
        return cast(CaseLog, log)

    def get_log_internal(self, *, log_id: int) -> Any:
        try:
            return CaseLog.objects.select_related("actor", "case").prefetch_related("attachments").get(id=log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError(f"日志 {log_id} 不存在") from None
