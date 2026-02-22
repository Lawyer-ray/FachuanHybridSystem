"""
Prompt 版本管理 Admin 配置

Requirements: 5.2
"""

import logging
from typing import Any, ClassVar

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.documents.models import PromptVersion

logger = logging.getLogger(__name__)


def _get_prompt_version_service() -> Any:
    """工厂函数获取 Prompt 版本服务"""
    from apps.documents.services.generation.prompt_version_service import PromptVersionService

    return PromptVersionService()


@admin.register(PromptVersion)
class PromptVersionAdmin(admin.ModelAdmin):
    """
    Prompt 版本管理

    提供 Prompt 模板版本的 CRUD 操作,支持版本激活和切换.
    """

    list_display: ClassVar = [
        "name",
        "version",
        "is_active_badge",
        "description_short",
        "created_at",
    ]

    list_filter: ClassVar = [
        "name",
        "is_active",
        "created_at",
    ]

    search_fields: ClassVar = [
        "name",
        "version",
        "description",
    ]

    ordering: ClassVar = ["-created_at"]

    readonly_fields: ClassVar = [
        "created_at",
        "updated_at",
    ]

    fieldsets: ClassVar = [
        (_("基本信息"), {"fields": ("name", "version", "is_active")}),
        (_("模板内容"), {"fields": ("template", "description")}),
        (
            _("时间信息"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    ]

    actions: ClassVar = ["activate_version"]

    @admin.display(description=_("状态"))
    def is_active_badge(self, obj: PromptVersion) -> Any:
        """显示激活状态徽章"""
        if obj.is_active:
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', "✓ 激活")
        return format_html('<span style="color: gray;">{}</span>', "○ 未激活")

    @admin.display(description=_("版本说明"))
    def description_short(self, obj: Any) -> Any:
        """显示简短描述"""
        if not obj.description:
            return "-"
        if len(obj.description) > 50:
            return obj.description[:50] + "..."
        return obj.description

    @admin.action(description=_("激活选中的版本"))
    def activate_version(self, request: Any, queryset: Any) -> None:
        """激活选中的版本"""
        if queryset.count() != 1:
            self.message_user(request, _("请选择一个版本进行激活"), level="error")
            return

        version = queryset.first()
        service = _get_prompt_version_service()

        try:
            service.activate_version(version.id)
            self.message_user(request, _("已激活版本:%(version)s") % {"version": version})
        except Exception as e:
            logger.exception("操作失败")
            self.message_user(request, _("激活失败:%(error)s") % {"error": e}, level="error")
