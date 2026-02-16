"""Business logic services."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import transaction

from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException

from apps.cases.models import Case, CaseLog, CaseLogVersion

from .case_log_query_service import CaseLogQueryService


class CaseLogMutationService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

    def create_log(
        self,
        *,
        case_id: int,
        content: str,
        user=None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
        reminder_type: str | None = None,
        reminder_time: datetime | None = None,
    ) -> CaseLog:
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None

        if not perm_open_access:
            if not user or not getattr(user, "is_authenticated", False):
                raise ForbiddenError("用户未认证")
            self.query_service.access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message="无权限创建此案件日志",
            )

        actor_id = getattr(user, "id", None) if user else None
        if not actor_id:
            raise ValidationException("操作人不能为空", errors={"actor": "缺少有效的操作人"})

        return CaseLog.objects.create(case_id=case_id, content=content, actor_id=actor_id)

    @transaction.atomic
    def update_log(
        self,
        *,
        log_id: int,
        data: dict[str, Any],
        user=None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> CaseLog:
        log = self.query_service.get_log_internal(log_id=log_id)

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=log.case,
                message="无权限修改此日志",
            )

        old_content = log.content
        actor_id = getattr(user, "id", None) if user else None

        for key, value in data.items():
            setattr(log, key, value)
        log.save()

        if "content" in data and data.get("content") != old_content:
            CaseLogVersion.objects.create(log=log, content=old_content, actor_id=actor_id)

        return log

    def delete_log(
        self,
        *,
        log_id: int,
        user=None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        log = self.query_service.get_log_internal(log_id=log_id)

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=log.case,
                message="无权限删除此日志",
            )

        log.delete()
        return {"success": True}
