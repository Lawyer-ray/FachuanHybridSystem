"""
法院 Admin

提供 Django Admin 界面来管理法院数据,包括初始化、查看层级结构等功能.
"""

import asyncio
import logging
from typing import Any

from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from apps.core.models import Court

logger = logging.getLogger(__name__)


def _get_initialization_service() -> Any:
    """工厂函数:创建初始化服务实例"""
    from apps.core.services.cause_court_initialization_service import CauseCourtInitializationService

    return CauseCourtInitializationService()


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin[Court]):
    """
    法院管理 Admin

    功能:
    - 查看所有法院数据
    - 按省份、层级、状态过滤
    - 显示层级结构
    - 初始化法院数据(从法院系统 API 获取)
    """

    list_display = [
        "code",
        "name",
        "level",
        "parent_display",
        "status_display",
        "updated_at",
    ]

    list_filter = [
        "level",
        "is_active",
    ]

    search_fields = [
        "code",
        "name",
    ]

    readonly_fields = [
        "code",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "code",
                    "name",
                    "level",
                    "parent",
                )
            },
        ),
        (
            _("状态"),
            {"fields": ("is_active",)},
        ),
        (
            _("时间信息"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    ordering = ["province", "level", "name"]

    list_per_page = 50

    def parent_display(self, obj: Court) -> SafeString:
        """显示父级法院"""
        if obj.parent:
            return format_html(
                '<span title="{}">{}</span>',
                obj.parent.full_path,
                obj.parent.name,
            )
        return mark_safe('<span style="color: #999;">—</span>')

    parent_display.short_description = _("上级法院")  # type: ignore[attr-defined]

    def status_display(self, obj: Court) -> SafeString:
        """状态显示"""
        if not obj.is_active:
            return mark_safe('<span style="color: #ffc107;">⏸️ 已禁用</span>')
        return mark_safe('<span style="color: #28a745;">✅ 正常</span>')

    status_display.short_description = _("状态")  # type: ignore[attr-defined]

    def get_urls(self) -> list[URLPattern]:
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls: list[URLPattern] = [
            path(
                "initialize/",
                self.admin_site.admin_view(self.initialize_courts_view),
                name="core_court_initialize",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        """自定义列表页面"""
        ctx: dict[str, Any] = extra_context or {}

        total_count = Court.objects.count()
        active_count = Court.objects.filter(is_active=True).count()

        # mypy 1.8.0 对 values().annotate() 链有内部错误，用 getattr 绕过
        _court_mgr: Any = Court.objects
        province_stats: list[Any] = list(
            _court_mgr.values("province").annotate(count=Count("id")).order_by("-count")[:10]
        )
        level_stats: list[Any] = list(_court_mgr.values("level").annotate(count=Count("id")).order_by("level"))

        ctx["statistics"] = {
            "total_count": total_count,
            "active_count": active_count,
            "province_stats": province_stats,
            "level_stats": level_stats,
        }
        ctx["show_initialize_button"] = True

        return super().changelist_view(request, extra_context=ctx)

    def initialize_courts_view(self, request: HttpRequest) -> HttpResponseRedirect:
        """初始化法院数据视图"""
        try:
            service = _get_initialization_service()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(service.initialize_courts())
            finally:
                loop.close()

            if result.success:
                msg = f"法院数据初始化成功!新增 {result.created} 条,更新 {result.updated} 条,删除 {result.deleted} 条."
                messages.success(request, msg)
                for warning in result.warnings:
                    messages.warning(request, warning)
            else:
                msg = (
                    f"法院数据初始化部分失败.新增 {result.created} 条,"
                    f"更新 {result.updated} 条,失败 {result.failed} 条."
                )
                messages.warning(request, msg)
                for error in result.errors[:5]:
                    messages.error(request, error)

        except Exception as e:
            logger.exception("初始化法院数据失败")
            messages.error(request, f"初始化法院数据失败: {e}")

        return HttpResponseRedirect(reverse("admin:core_court_changelist"))

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁用手动添加功能(数据应通过初始化导入)"""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Court | None = None) -> bool:
        """禁用删除功能(数据应通过初始化管理)"""
        return False
