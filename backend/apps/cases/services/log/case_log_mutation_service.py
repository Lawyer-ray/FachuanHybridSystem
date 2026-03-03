"""Business logic services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog, CaseLogVersion
from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException

from .case_log_query_service import CaseLogQueryService


class CaseLogMutationService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

    def create_log(
        self,
        *,
        case_id: int,
        content: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        reminder_type: str | None = None,
        reminder_time: datetime | None = None,
    ) -> CaseLog:
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(case_id)s 不存在") % {"case_id": case_id}) from None

        if not perm_open_access:
            if not user or not getattr(user, "is_authenticated", False):
                raise ForbiddenError(_("用户未认证"))
            self.query_service.access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message=_("无权限创建此案件日志"),
            )

        actor_id = getattr(user, "id", None) if user else None
        if not actor_id:
            raise ValidationException(_("操作人不能为空"), errors={"actor": _("缺少有效的操作人")})

        log = CaseLog.objects.create(case_id=case_id, content=content, actor_id=actor_id)

        if reminder_type and reminder_time:
            from apps.core.interfaces import ServiceLocator

            reminder_service = ServiceLocator.get_reminder_service()
            reminder_service.create_reminder(
                case_log_id=log.id,
                reminder_type=reminder_type,
                content=content,
                due_at=reminder_time,
            )

        return log

    @transaction.atomic
    def update_log(
        self,
        *,
        log_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
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
                message=_("无权限修改此日志"),
            )

        old_content = log.content
        actor_id = getattr(user, "id", None) if user else None

        for key, value in data.items():
            setattr(log, key, value)
        log.save()

        if "content" in data and data.get("content") != old_content:
            CaseLogVersion.objects.create(log=log, content=old_content, actor_id=actor_id)

        return cast(CaseLog, log)

    def delete_log(
        self,
        *,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
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
                message=_("无权限删除此日志"),
            )

        log.delete()
        return {"success": True}
