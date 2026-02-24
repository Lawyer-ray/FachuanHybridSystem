"""
AccountCredential Admin - 账号凭证管理
遵循 Admin 层规范：UI配置、显示格式化，业务逻辑委托给 Service
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.organization.models import AccountCredential
from apps.organization.services import AccountCredentialService

_credential_service = AccountCredentialService()


@admin.register(AccountCredential)
class AccountCredentialAdmin(admin.ModelAdmin[AccountCredential]):

    list_display: ClassVar[list[str]] = [
        "id",
        "lawyer",
        "site_name",
        "account",
        "is_preferred",
        "created_at",
    ]

    search_fields: ClassVar[tuple[str, ...]] = (
        "site_name", "url", "account", "lawyer__username", "lawyer__real_name"
    )

    list_filter: ClassVar[list[str]] = [
        "site_name", "is_preferred", "lawyer", "last_login_success_at", "created_at"
    ]

    autocomplete_fields: ClassVar[tuple[str, ...]] = ("lawyer",)

    readonly_fields: ClassVar[list[str]] = [
        "id",
        "login_statistics_display",
        "success_rate_display",
        "last_login_display",
        "created_at",
        "updated_at",
    ]

    fieldsets: ClassVar[tuple[Any, ...]] = (
        (_("基本信息"), {"fields": ("id", "lawyer", "site_name", "url", "account", "password")}),
        (
            _("登录统计"),
            {"fields": ("login_statistics_display", "success_rate_display", "last_login_display", "is_preferred")},
        ),
        (_("时间信息"), {"fields": ("created_at", "updated_at")}),
    )

    ordering: ClassVar[list[str]] = ["-last_login_success_at", "-login_success_count", "login_failure_count"]

    date_hierarchy = "last_login_success_at"

    list_per_page = 50

    actions: ClassVar[list[str]] = ["mark_as_preferred", "unmark_as_preferred"]

    def get_form(self, request: HttpRequest, obj: AccountCredential | None = None, **kwargs: Any) -> type[forms.ModelForm]:  # type: ignore[override]
        form = super().get_form(request, obj, **kwargs)
        if "password" in form.base_fields:
            form.base_fields["password"].widget = forms.PasswordInput(render_value=True)
        return form

    @admin.display(description=_("成功/失败次数"))
    def login_statistics_display(self, obj: AccountCredential) -> SafeString:
        return format_html(
            '<span style="color: #28a745; font-weight: bold;">{}</span> / <span style="color: #dc3545;">{}</span>',
            obj.login_success_count,
            obj.login_failure_count,
        )

    @admin.display(description=_("成功率"))
    def success_rate_display(self, obj: AccountCredential) -> SafeString:
        rate = obj.success_rate * 100

        if rate >= 80:
            color = "#28a745"
        elif rate >= 50:
            color = "#ffc107"
        else:
            color = "#dc3545"

        rate_str = f"{rate:.1f}%"

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, rate_str)

    @admin.display(description=_("最后成功登录"))
    def last_login_display(self, obj: AccountCredential) -> SafeString:
        if not obj.last_login_success_at:
            return format_html('<span style="color: #999;">{}</span>', _("从未成功"))

        now = timezone.now()
        delta = now - obj.last_login_success_at

        if delta.days > 30:
            color = "#dc3545"
            time_str = str(_("%(days)d天前")) % {"days": delta.days}
        elif delta.days > 7:
            color = "#ffc107"
            time_str = str(_("%(days)d天前")) % {"days": delta.days}
        elif delta.days > 0:
            color = "#007bff"
            time_str = str(_("%(days)d天前")) % {"days": delta.days}
        else:
            hours = delta.seconds // 3600
            if hours > 0:
                color = "#28a745"
                time_str = str(_("%(hours)d小时前")) % {"hours": hours}
            else:
                minutes = delta.seconds // 60
                color = "#28a745"
                time_str = str(_("%(minutes)d分钟前")) % {"minutes": minutes}

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, time_str)

    @admin.display(description=_("操作"))
    def auto_login_button(self, obj: AccountCredential) -> SafeString:
        if obj.site_name == "court_zxfw":
            url = reverse("admin:automation_tokenacquisitionhistory_changelist")
            return format_html(
                '<a class="button" href="{}?credential_id={}" '
                'style="background-color: #28a745; color: white; padding: 5px 8px; '
                'border-radius: 4px; text-decoration: none; display: inline-block; font-size: 12px;">'
                "📊 查看历史</a>",
                url,
                obj.id,
            )
        else:
            return format_html('<span style="color: #999;">{}</span>', _("不支持"))

    @admin.action(description=_("标记为优先账号"))
    def mark_as_preferred(
        self, request: HttpRequest, queryset: QuerySet[AccountCredential]
    ) -> None:
        credential_ids: list[int] = list(queryset.values_list("id", flat=True))
        count: int = _credential_service.batch_mark_preferred(credential_ids)
        self.message_user(
            request,
            _("已将 %(count)d 个账号标记为优先使用") % {"count": count},
        )

    @admin.action(description=_("取消优先标记"))
    def unmark_as_preferred(
        self, request: HttpRequest, queryset: QuerySet[AccountCredential]
    ) -> None:
        credential_ids: list[int] = list(queryset.values_list("id", flat=True))
        count: int = _credential_service.batch_unmark_preferred(credential_ids)
        self.message_user(
            request,
            _("已取消 %(count)d 个账号的优先标记") % {"count": count},
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[AccountCredential]:
        return super().get_queryset(request).select_related("lawyer")
