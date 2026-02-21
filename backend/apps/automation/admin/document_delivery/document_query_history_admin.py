"""
文书查询历史 Django Admin 界面

提供查询历史记录管理、搜索、过滤等功能。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models import DocumentQueryHistory

logger = logging.getLogger("apps.automation")


@admin.register(DocumentQueryHistory)
class DocumentQueryHistoryAdmin(admin.ModelAdmin[DocumentQueryHistory]):
    """文书查询历史管理"""

    list_display: ClassVar[list[str]] = [
        "id",
        "credential_display",
        "case_number",
        "send_time_display",
        "court_sms_display",
        "queried_at_display",
    ]

    list_filter: ClassVar[list[Any]] = [
        "send_time",
        "queried_at",
        ("credential", admin.RelatedFieldListFilter),
        ("court_sms", admin.RelatedFieldListFilter),
    ]

    search_fields: ClassVar[list[str]] = [
        "case_number",
        "credential__account",
        "credential__site_name",
    ]

    ordering: ClassVar[list[str]] = ["-queried_at"]
    list_per_page = 50

    readonly_fields: ClassVar[list[str]] = [
        "id",
        "credential",
        "case_number",
        "send_time",
        "court_sms",
        "queried_at",
        "court_sms_link",
        "time_since_query",
    ]

    fieldsets: ClassVar[tuple[Any, ...]] = (
        (
            _("查询信息"),
            {"fields": ("id", "credential", "case_number", "send_time")},
        ),
        (
            _("关联信息"),
            {"fields": ("court_sms", "court_sms_link")},
        ),
        (
            _("时间信息"),
            {"fields": ("queried_at", "time_since_query")},
        ),
    )

    date_hierarchy = "queried_at"

    @admin.display(description=_("账号凭证"))
    def credential_display(self, obj: DocumentQueryHistory) -> SafeString | str:
        """账号凭证显示"""
        if obj.credential:
            url = reverse("admin:organization_accountcredential_change", args=[obj.credential.id])
            return format_html(
                '<a href="{}" target="_blank">{}</a><br><small style="color: #666;">{}</small>',
                url,
                obj.credential.account,
                obj.credential.site_name,
            )
        return "-"

    @admin.display(description=_("文书发送时间"))
    def send_time_display(self, obj: DocumentQueryHistory) -> SafeString:
        """文书发送时间显示"""
        now = timezone.now()
        time_diff = now - obj.send_time

        if time_diff.days > 0:
            time_str = f"{time_diff.days} 天前"
            color = "#666"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            time_str = f"{hours} 小时前"
            color = "#666"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            time_str = f"{minutes} 分钟前"
            color = "blue"
        else:
            time_str = "刚刚"
            color = "green"

        return format_html(
            '<span style="color: {};">{}</span><br><small style="color: #666;">{}</small>',
            color,
            time_str,
            obj.send_time.strftime("%Y-%m-%d %H:%M"),
        )

    @admin.display(description=_("关联短信"))
    def court_sms_display(self, obj: DocumentQueryHistory) -> SafeString:
        """关联短信显示"""
        if obj.court_sms:
            url = reverse("admin:automation_courtsms_change", args=[obj.court_sms.id])

            status_colors = {
                "pending": "orange",
                "parsing": "blue",
                "downloading": "blue",
                "download_failed": "red",
                "matching": "blue",
                "pending_manual": "orange",
                "renaming": "blue",
                "notifying": "blue",
                "completed": "green",
                "failed": "red",
            }
            color = status_colors.get(obj.court_sms.status, "gray")

            return format_html(
                '<a href="{}" target="_blank">短信 #{}</a><br><small style="color: {};">{}</small>',
                url,
                obj.court_sms.id,
                color,
                obj.court_sms.get_status_display(),
            )
        return format_html('<span style="color: gray;">{}</span>', "无关联短信")

    @admin.display(description=_("查询时间"))
    def queried_at_display(self, obj: DocumentQueryHistory) -> SafeString:
        """查询时间显示"""
        now = timezone.now()
        time_diff = now - obj.queried_at

        if time_diff.days > 0:
            time_str = f"{time_diff.days} 天前"
            color = "#666"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            time_str = f"{hours} 小时前"
            color = "#666"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            time_str = f"{minutes} 分钟前"
            color = "blue"
        else:
            time_str = "刚刚"
            color = "green"

        return format_html(
            '<span style="color: {};">{}</span><br><small style="color: #666;">{}</small>',
            color,
            time_str,
            obj.queried_at.strftime("%Y-%m-%d %H:%M"),
        )

    @admin.display(description=_("关联短信链接"))
    def court_sms_link(self, obj: DocumentQueryHistory) -> SafeString | str:
        """关联短信链接"""
        if obj.court_sms:
            url = reverse("admin:automation_courtsms_change", args=[obj.court_sms.id])
            return format_html(
                '<a href="{}" target="_blank">查看短信 #{} - {}</a>',
                url,
                obj.court_sms.id,
                obj.court_sms.get_status_display(),
            )
        return "-"

    @admin.display(description=_("查询后经过时间"))
    def time_since_query(self, obj: DocumentQueryHistory) -> str:
        """查询后经过的时间"""
        now = timezone.now()
        time_diff = now - obj.queried_at

        total_seconds = int(time_diff.total_seconds())
        days = time_diff.days
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if days > 0:
            return f"{days} 天 {hours % 24} 小时前"
        elif hours > 0:
            return f"{hours} 小时 {minutes} 分钟前"
        elif minutes > 0:
            return f"{minutes} 分钟前"
        else:
            return "刚刚"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DocumentQueryHistory | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DocumentQueryHistory | None = None
    ) -> bool:
        return True

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        """自定义批量操作"""
        actions = super().get_actions(request)
        actions["delete_old_records"] = (self.delete_old_records, "delete_old_records", _("删除30天前的记录"))
        return actions

    def delete_old_records(
        self, request: HttpRequest, queryset: QuerySet[DocumentQueryHistory]
    ) -> None:
        """批量删除30天前的记录"""
        cutoff_date = timezone.now() - timedelta(days=30)
        old_records = queryset.filter(queried_at__lt=cutoff_date)
        count = old_records.count()

        old_records.delete()

        self.message_user(request, _(f"成功删除 {count} 条30天前的查询记录"))
        logger.info(f"管理员批量删除旧查询记录: Count={count}, User={request.user}")

    def get_queryset(self, request: HttpRequest) -> QuerySet[DocumentQueryHistory]:
        """优化查询性能"""
        return super().get_queryset(request).select_related("credential", "court_sms")

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[DocumentQueryHistory], search_term: str
    ) -> tuple[QuerySet[DocumentQueryHistory], bool]:
        """自定义搜索，支持案号模糊匹配"""
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)

        if search_term and ("(" in search_term or "）" in search_term or "年" in search_term):
            queryset |= self.model.objects.filter(
                case_number__icontains=search_term.replace("(", "").replace(")", "").replace("（", "").replace("）", "")
            )
            may_have_duplicates = True

        return queryset, may_have_duplicates
