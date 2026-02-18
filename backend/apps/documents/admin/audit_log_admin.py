"""
审计日志 Admin 配置

Requirements: 6.6
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.documents.models import TemplateAuditLog


@admin.register(TemplateAuditLog)
class TemplateAuditLogAdmin(admin.ModelAdmin[TemplateAuditLog]):
    """
    模板审计日志管理

    只读界面,用于查看模板修改历史.
    """

    list_display = (
        "id",
        "content_type",
        "object_id",
        "object_repr_display",
        "action",
        "user",
        "created_at",
    )

    list_filter = (
        "content_type",
        "action",
        "created_at",
    )

    search_fields = (
        "object_repr",
        "user__name",
    )

    readonly_fields = (
        "content_type",
        "object_id",
        "object_repr",
        "action",
        "changes_display",
        "user",
        "ip_address",
        "user_agent",
        "created_at",
    )

    ordering = ("-created_at",)

    date_hierarchy: str = "created_at"

    fieldsets = (
        (_("对象信息"), {"fields": ("content_type", "object_id", "object_repr")}),
        (_("操作信息"), {"fields": ("action", "changes_display")}),
        (_("操作人信息"), {"fields": ("user", "ip_address", "user_agent")}),
        (_("时间"), {"fields": ("created_at",)}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁止手动添加"""
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """禁止修改"""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """禁止删除"""
        return False

    def object_repr_display(self, obj: TemplateAuditLog) -> str:
        """显示对象描述(截断)"""
        text = obj.object_repr
        if len(text) > 50:
            text = text[:50] + "..."
        return text

    object_repr_display.short_description = _("对象描述")  # type: ignore[attr-defined]

    def changes_display(self, obj: TemplateAuditLog) -> Any:
        """格式化显示变更内容"""
        if not obj.changes:
            return _("无变更记录")

        html_parts = [
            '<div style="background: #f5f5f5; padding: 10px; border-radius: 4px; max-height: 400px; overflow-y: auto;">'
        ]
        html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
        html_parts.append('<tr style="background: #e0e0e0;">')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ccc;">字段</th>')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ccc;">旧值</th>')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ccc;">新值</th>')
        html_parts.append("</tr>")

        for field, change in obj.changes.items():
            old_val = change.get("old", "-")
            new_val = change.get("new", "-")

            # 截断过长的值
            if isinstance(old_val, str) and len(old_val) > 100:
                old_val = old_val[:100] + "..."
            if isinstance(new_val, str) and len(new_val) > 100:
                new_val = new_val[:100] + "..."

            html_parts.append(
                format_html(
                    "<tr>"
                    '<td style="padding: 8px; border: 1px solid #ccc; font-weight: bold;">{}</td>'
                    '<td style="padding: 8px; border: 1px solid #ccc; color: #c62828;">{}</td>'
                    '<td style="padding: 8px; border: 1px solid #ccc; color: #2e7d32;">{}</td>'
                    "</tr>",
                    field,
                    old_val,
                    new_val,
                )
            )

        html_parts.append("</table>")
        html_parts.append("</div>")

        return mark_safe("".join(str(p) for p in html_parts))

    changes_display.short_description = _("变更详情")  # type: ignore[attr-defined]
