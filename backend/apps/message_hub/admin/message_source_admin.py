"""MessageSource Admin — 消息来源管理。"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.message_hub.models import MessageSource, SyncStatus


@admin.register(MessageSource)
class MessageSourceAdmin(admin.ModelAdmin[MessageSource]):
    list_display = [
        "id",
        "display_name",
        "source_type_badge",
        "credential",
        "is_enabled",
        "poll_interval_minutes",
        "sync_status_badge",
        "last_sync_at",
        "refresh_button",
    ]
    list_filter: ClassVar = ["source_type", "is_enabled", "last_sync_status"]
    search_fields: ClassVar = ("display_name", "credential__account", "credential__site_name")
    autocomplete_fields: ClassVar = ("credential",)
    readonly_fields: ClassVar = ["last_sync_at", "last_sync_status", "last_sync_error", "last_synced_uid", "created_at"]

    fieldsets: ClassVar = (
        (
            _("基本配置"),
            {
                "fields": (
                    "display_name",
                    "credential",
                    "source_type",
                    "is_enabled",
                    "poll_interval_minutes",
                    "sync_since",
                )
            },
        ),
        (
            _("发件人过滤"),
            {
                "fields": ("sender_whitelist", "sender_blacklist"),
                "description": _("可输入邮箱地址或发件人名称，每行一个，大小写不敏感。白名单优先于黑名单。"),
            },
        ),
        (_("IMAP 配置"), {"fields": ("imap_host", "imap_account"), "classes": ("collapse",)}),
        (
            _("同步状态"),
            {"fields": ("last_sync_at", "last_sync_status", "last_sync_error", "last_synced_uid", "created_at")},
        ),
    )

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path("<int:pk>/sync/", self.admin_site.admin_view(self._sync_view), name="message_hub_messagesource_sync"),
        ]
        return custom + urls

    def _sync_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        from django.shortcuts import redirect
        from django_q.tasks import async_task

        async_task("apps.message_hub.tasks.sync_source_by_id", pk)
        self.message_user(request, _("同步任务已提交，稍后刷新查看结果"), messages.SUCCESS)
        return redirect("..")

    @admin.display(description=_("来源类型"))
    def source_type_badge(self, obj: MessageSource) -> SafeString:
        colors = {"imap": "#007bff", "court_inbox": "#6f42c1", "court_schedule": "#e85d04"}
        color = colors.get(obj.source_type, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{}</span>',
            color,
            obj.get_source_type_display(),
        )

    @admin.display(description=_("同步状态"))
    def sync_status_badge(self, obj: MessageSource) -> SafeString:
        colors = {SyncStatus.SUCCESS: "#28a745", SyncStatus.FAILED: "#dc3545", SyncStatus.PENDING: "#6c757d"}
        color = colors.get(obj.last_sync_status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{}</span>',
            color,
            obj.get_last_sync_status_display(),
        )

    @admin.display(description=_("操作"))
    def refresh_button(self, obj: MessageSource) -> SafeString:
        from django.urls import reverse

        url = reverse("admin:message_hub_messagesource_sync", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="background:#17a2b8;color:#fff;padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px">立即同步</a>',
            url,
        )
