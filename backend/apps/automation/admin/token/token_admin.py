"""
Token 管理 Admin
提供 Token 的查看、搜索、过滤功能
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models import CourtToken

SITE_NAME_LABELS: dict[str, str] = {
    "court_zxfw": "人民法院在线服务网（一张网）",
    "court_baoquan": "人民法院保全系统",
}


@admin.register(CourtToken)
class CourtTokenAdmin(admin.ModelAdmin[CourtToken]):
    """
    一张网/保全系统 Token 管理 Admin

    功能：
    - 查看所有一张网/保全系统 Token
    - 按网站、账号搜索
    - 按过期状态过滤
    - 显示 Token 状态（有效/过期）
    """

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        """隐藏 Admin 首页入口，但保留直接 URL 访问能力"""
        return {}

    list_display = [
        "id",
        "site_name_display",
        "account",
        "token_preview",
        "token_type",
        "status_display",
        "expires_at",
        "created_at",
        "updated_at",
    ]

    list_filter = [
        "site_name",
        "token_type",
        "created_at",
        "expires_at",
    ]

    search_fields = [
        "site_name",
        "account",
        "token",
    ]

    readonly_fields = [
        "id",
        "token_full",
        "status_display",
        "remaining_time",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            _("基本信息"),
            {
                "description": _("该模块用于管理人民法院在线服务网（一张网）和保全系统的认证Token。"),
                "fields": ("id", "site_name", "account", "token_type"),
            },
        ),
        (_("Token 信息"), {"fields": ("token_full", "status_display", "remaining_time")}),
        (_("时间信息"), {"fields": ("expires_at", "created_at", "updated_at")}),
    )

    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    list_per_page = 50

    @admin.display(description=_("站点"))
    def site_name_display(self, obj: CourtToken) -> str:
        """显示可读站点名称"""
        return SITE_NAME_LABELS.get(obj.site_name, obj.site_name)  # type: ignore[no-any-return]

    @admin.display(description=_("Token 预览"))
    def token_preview(self, obj: CourtToken) -> str:
        """Token 预览（只显示前20个字符）"""
        if len(obj.token) > 20:
            return f"{obj.token[:20]}..."
        return obj.token  # type: ignore[no-any-return]

    @admin.display(description=_("完整 Token"))
    def token_full(self, obj: CourtToken) -> SafeString:
        """完整的 Token（在详情页显示）"""
        return format_html(
            '<textarea readonly style="width: 100%; height: 100px; '
            "font-family: monospace; font-size: 12px; padding: 10px; "
            'border: 1px solid #ddd; border-radius: 4px;">{}</textarea>',
            obj.token,
        )

    @admin.display(description=_("状态"))
    def status_display(self, obj: CourtToken) -> SafeString:
        """显示 Token 状态（有效/过期）"""
        if obj.is_expired():
            return format_html('<span style="color: red; font-weight: bold;">{}</span>', "❌ 已过期")
        else:
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', "✅ 有效")

    @admin.display(description=_("剩余时间"))
    def remaining_time(self, obj: CourtToken) -> SafeString:
        """剩余有效时间"""
        if obj.is_expired():
            return format_html('<span style="color: red;">{}</span>', "已过期")

        now = timezone.now()
        remaining = obj.expires_at - now

        total_seconds = int(remaining.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            time_str = f"{hours} 小时 {minutes} 分钟"
        elif minutes > 0:
            time_str = f"{minutes} 分钟 {seconds} 秒"
        else:
            time_str = f"{seconds} 秒"

        if total_seconds < 300:
            color = "red"
        elif total_seconds < 1800:
            color = "orange"
        else:
            color = "green"

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, time_str)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁用添加功能（Token 由系统自动创建）"""
        return False

    def has_change_permission(self, request: HttpRequest, obj: CourtToken | None = None) -> bool:
        """禁用修改功能（Token 由系统管理）"""
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        """自定义批量操作"""
        actions = super().get_actions(request)

        actions["delete_expired_tokens"] = (  # type: ignore[assignment]
            self.delete_expired_tokens,
            "delete_expired_tokens",
            _("删除已过期的一张网/保全Token"),
        )

        return actions

    def delete_expired_tokens(self, request: HttpRequest, queryset: QuerySet[CourtToken]) -> None:
        """批量删除过期的一张网/保全Token"""
        expired_tokens = [token for token in queryset if token.is_expired()]
        count = len(expired_tokens)

        for token in expired_tokens:
            token.delete()

        self.message_user(request, _(f"成功删除 {count} 个已过期的一张网/保全Token"))
