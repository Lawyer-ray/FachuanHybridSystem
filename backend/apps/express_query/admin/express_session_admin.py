"""快递账号会话 Admin —— 每个律师在各承运商的扫码登录态。"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html

from apps.express_query.models import ExpressSession, ExpressSessionStatus

logger = logging.getLogger("apps.express_query")


@admin.register(ExpressSession)
class ExpressSessionAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display: ClassVar[list[str]] = [
        "lawyer",
        "carrier_type",
        "status_badge",
        "last_login_at",
        "last_verified_at",
        "last_error_short",
    ]
    list_filter: ClassVar[list[str]] = ["carrier_type", "status"]
    search_fields: ClassVar[list[str]] = ["lawyer__username", "lawyer__first_name", "lawyer__last_name"]
    readonly_fields: ClassVar[list[str]] = [
        "profile_key_display",
        "last_login_at",
        "last_verified_at",
        "last_error",
        "created_at",
        "updated_at",
    ]
    actions: ClassVar[list[str]] = ["action_open_login", "action_mark_expired"]
    ordering: ClassVar[list[str]] = ["lawyer_id", "carrier_type"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.display(description="状态")
    def status_badge(self, obj: ExpressSession) -> str:
        colors = {
            ExpressSessionStatus.ACTIVE: "#2e7d32",
            ExpressSessionStatus.EXPIRED: "#c62828",
            ExpressSessionStatus.EMPTY: "#757575",
        }
        color = colors.get(obj.status)  # type: ignore[arg-type]
        return format_html(
            '<span style="color:#fff;background:{};padding:2px 8px;border-radius:10px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="浏览器目录")
    def profile_key_display(self, obj: ExpressSession) -> str:
        return obj.profile_key

    @admin.display(description="最后错误")
    def last_error_short(self, obj: ExpressSession) -> str:
        return (obj.last_error or "")[:60]

    @admin.action(description="打开浏览器扫码登录")
    def action_open_login(self, request: HttpRequest, queryset: QuerySet[ExpressSession]) -> None:
        from apps.express_query.services.session_service import enqueue_login_helper

        count = 0
        for session in queryset:
            enqueue_login_helper(session.lawyer_id, session.carrier_type)
            count += 1

        self.message_user(
            request,
            f"已提交 {count} 个扫码任务，请在弹出的浏览器窗口中扫码；完成后状态会自动变为「已登录」。",
            messages.SUCCESS,
        )

    @admin.action(description="标记为已失效（下次查询将要求重新扫码）")
    def action_mark_expired(self, request: HttpRequest, queryset: QuerySet[ExpressSession]) -> None:
        updated = queryset.update(
            status=ExpressSessionStatus.EXPIRED,
            last_error="管理员手动标记失效",
            updated_at=timezone.now(),
        )
        self.message_user(request, f"已将 {updated} 个会话标记为失效。", messages.WARNING)
