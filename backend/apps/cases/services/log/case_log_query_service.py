"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.db.models import QuerySet

from apps.cases.models import Case, CaseLog
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.exceptions import NotFoundError

from .case_log_query_repo import CaseLogQueryRepo

logger = logging.getLogger("apps.cases")


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
    ) -> QuerySet[CaseLog, CaseLog]:
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

    def list_logs_with_reminders(
        self,
        *,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLog]:
        """取日志列表并批量预热提醒缓存（单次查询，供 API 序列化）。

        async 视图里 Ninja 序列化不能触发同步 ORM；逐条预热是 N+1，
        这里用批量导出接口一次取全，写进每个对象已有的缓存属性。
        """
        objs = list(
            self.list_logs(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )
        )
        self.warm_reminder_cache(objs)
        return objs

    @staticmethod
    def warm_reminder_cache(objs: list[CaseLog]) -> None:
        """把批量提醒结果写入对象的 _cached_exported_reminders（幂等，零额外查询时跳过）。"""
        if not objs:
            return
        from apps.core.interfaces import ServiceLocator

        try:
            reminder_service = ServiceLocator.get_reminder_service()
            rows_by_log = reminder_service.export_case_log_reminders_batch_internal(
                case_log_ids=[obj.id for obj in objs if obj.id]
            )
        except Exception:
            logger.exception("批量预热日志提醒失败", extra={"count": len(objs)})
            return
        for obj in objs:
            obj._cached_exported_reminders = rows_by_log.get(obj.id, [])

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
            message="无权限访问此日志",
        )
        return cast(CaseLog, log)

    def get_log_internal(self, *, log_id: int) -> Any:
        try:
            return CaseLog.objects.select_related("actor", "case").prefetch_related("attachments").get(id=log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError("日志 %(log_id)s 不存在" % {"log_id": log_id}) from None
