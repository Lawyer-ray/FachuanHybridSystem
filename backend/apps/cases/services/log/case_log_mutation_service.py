"""Business logic services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog, CaseLogVersion
from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException
from apps.reminders.services.reminder_service_adapter import CASE_LOG_API_REMINDER_SOURCE

from .case_log_query_service import CaseLogQueryService


class CaseLogMutationService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

    @transaction.atomic
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

        self._sync_case_log_reminder(
            log=log,
            actor_id=actor_id,
            reminder_type=reminder_type,
            reminder_time=reminder_time,
            content=content,
            clear_when_empty=False,
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

        reminder_type_provided = "reminder_type" in data
        reminder_time_provided = "reminder_time" in data
        if reminder_type_provided != reminder_time_provided:
            raise ValidationException(_("提醒类型和提醒时间必须同时提供"))

        reminder_type = data.pop("reminder_type", None) if reminder_type_provided else None
        reminder_time = data.pop("reminder_time", None) if reminder_time_provided else None

        old_content = log.content
        actor_id = getattr(user, "id", None) if user else None

        for key, value in data.items():
            setattr(log, key, value)
        log.save()

        if "content" in data and data.get("content") != old_content:
            CaseLogVersion.objects.create(log=log, content=old_content, actor_id=actor_id)

        if reminder_type_provided and reminder_time_provided:
            self._sync_case_log_reminder(
                log=log,
                actor_id=actor_id,
                reminder_type=cast(str | None, reminder_type),
                reminder_time=cast(datetime | None, reminder_time),
                content=log.content,
                clear_when_empty=True,
            )

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

    def _sync_case_log_reminder(
        self,
        *,
        log: CaseLog,
        actor_id: int | None,
        reminder_type: str | None,
        reminder_time: datetime | None,
        content: str,
        clear_when_empty: bool,
    ) -> None:
        from apps.core.interfaces import ServiceLocator

        reminder_service = ServiceLocator.get_reminder_service()

        if reminder_type is None and reminder_time is None:
            if not clear_when_empty:
                return
            reminder_service.clear_case_log_reminder_internal(
                case_log_id=int(log.id),
                metadata_source=CASE_LOG_API_REMINDER_SOURCE,
            )
            return

        if reminder_type is None or reminder_time is None:
            raise ValidationException(_("提醒类型和提醒时间必须同时为空或同时有值"))

        reminder_service.upsert_case_log_reminder_internal(
            case_log_id=int(log.id),
            reminder_type=reminder_type,
            content=content,
            reminder_time=reminder_time,
            user_id=actor_id,
            metadata_source=CASE_LOG_API_REMINDER_SOURCE,
        )
