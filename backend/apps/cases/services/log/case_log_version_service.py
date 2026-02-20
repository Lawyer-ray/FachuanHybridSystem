"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

from typing import Any

from apps.cases.models import CaseLogVersion

from .case_log_query_service import CaseLogQueryService


class CaseLogVersionService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

    def get_log_versions(
        self,
        *,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLogVersion]:
        log = self.query_service.get_log_internal(log_id=log_id)

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=log.case,
                message=_("无权限访问此日志版本"),
            )

        return list(CaseLogVersion.objects.filter(log_id=log_id).select_related("actor").order_by("-version_at"))
