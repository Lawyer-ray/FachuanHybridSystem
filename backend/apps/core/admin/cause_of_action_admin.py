"""
案由 Admin

提供 Django Admin 界面来管理案由数据,包括初始化、查看层级结构等功能.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.core.models import CauseOfAction

if TYPE_CHECKING:
    from apps.core.services.cause_court_initialization_service import CauseCourtInitializationService

logger = logging.getLogger(__name__)


def _get_initialization_service() -> CauseCourtInitializationService:
    """工厂函数:创建初始化服务实例"""
    from apps.core.services.cause_court_initialization_service import CauseCourtInitializationService

    return CauseCourtInitializationService()


@admin.register(CauseOfAction)
class CauseOfActionAdmin(admin.ModelAdmin[CauseOfAction]):
    """
    案由管理 Admin

    功能:
    - 查看所有案由数据
    - 按案件类型、层级、状态过滤
    - 显示层级结构
    - 初始化案由数据(从法院系统 API 获取)
    """

    list_display = [
        "code",
        "name",
        "case_type_display",
        "level",
        "parent_display",
        "status_display",
        "updated_at",
    ]

    list_filter = [
        "case_type",
        "level",
        "is_active",
        "is_deprecated",
    ]

    search_fields = [
        "code",
        "name",
    ]

    readonly_fields = [
        "code",
        "created_at",
        "updated_at",
        "deprecated_at",
    ]

    fieldsets: ClassVar[tuple[Any, ...]] = (
        (
            _("基本信息"),
            {
                "fields": (
                    "code",
                    "name",
                    "case_type",
                    "level",
                    "parent",
                )
            },
        ),
        (
            _("状态"),
            {
                "fields": (
                    "is_active",
                    "is_deprecated",
                    "deprecated_at",
                    "deprecated_reason",
                )
            },
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

    ordering = ["case_type", "level", "code"]

    list_per_page: ClassVar[int] = 50

    change_list_template = "admin/core/causeofaction/change_list.html"

    @admin.display(description=_("案件类型"), ordering="case_type")
    def case_type_display(self, obj: CauseOfAction) -> SafeString:
        """带颜色的案件类型显示"""
        color_map: dict[str, str] = {
            str(CauseOfAction.CaseType.CIVIL): "#28a745",
            str(CauseOfAction.CaseType.CRIMINAL): "#dc3545",
            str(CauseOfAction.CaseType.ADMINISTRATIVE): "#007bff",
        }
        color = color_map.get(str(obj.case_type), "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px;">{}</span>',
            color,
            obj.get_case_type_display(),
        )

    @admin.display(description=_("上级案由"))
    def parent_display(self, obj: CauseOfAction) -> SafeString:
        """显示父级案由"""
        if obj.parent:
            return format_html(
                '<span title="{}">{}</span>',
                obj.parent.full_path,
                obj.parent.name,
            )
        return format_html('<span style="color: #999;">{}</span>', "—")

    @admin.display(description=_("状态"))
    def status_display(self, obj: CauseOfAction) -> SafeString:
        """状态显示"""
        if obj.is_deprecated:
            return format_html('<span style="color: #dc3545;">{}</span>', "⚠️ 已废弃")
        if not obj.is_active:
            return format_html('<span style="color: #ffc107;">{}</span>', "⏸️ 已禁用")
        return format_html('<span style="color: #28a745;">{}</span>', "✅ 正常")

    def get_urls(self) -> list[URLPattern]:
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "initialize/",
                self.admin_site.admin_view(self.initialize_causes_view),
                name="core_causeofaction_initialize",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        """自定义列表页面"""
        extra_context = extra_context or {}

        # 统计信息
        total_count = CauseOfAction.objects.count()
        active_count = CauseOfAction.objects.filter(is_active=True, is_deprecated=False).count()
        deprecated_count = CauseOfAction.objects.filter(is_deprecated=True).count()

        # 按类型统计
        civil_count = CauseOfAction.objects.filter(case_type=CauseOfAction.CaseType.CIVIL).count()
        criminal_count = CauseOfAction.objects.filter(case_type=CauseOfAction.CaseType.CRIMINAL).count()
        administrative_count = CauseOfAction.objects.filter(case_type=CauseOfAction.CaseType.ADMINISTRATIVE).count()

        extra_context["statistics"] = {
            "total_count": total_count,
            "active_count": active_count,
            "deprecated_count": deprecated_count,
            "civil_count": civil_count,
            "criminal_count": criminal_count,
            "administrative_count": administrative_count,
        }
        extra_context["show_initialize_button"] = True

        return super().changelist_view(request, extra_context=extra_context)

    def initialize_causes_view(self, request: HttpRequest) -> HttpResponse:
        """初始化案由数据视图"""
        import concurrent.futures

        try:
            service = _get_initialization_service()

            def run_async_init() -> Any:
                """在独立线程中运行异步初始化"""
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(service.initialize_causes())
                finally:
                    loop.close()

            # 使用线程池执行器在独立线程中运行异步代码
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_init)
                result = future.result(timeout=300)  # 5分钟超时

            # 构建消息
            if result.success:
                msg = (
                    f"案由数据初始化成功!"
                    f"新增 {result.created} 条,"
                    f"更新 {result.updated} 条,"
                    f"废弃 {result.deprecated} 条,"
                    f"删除 {result.deleted} 条."
                )
                messages.success(request, msg)

                # 显示警告信息
                for warning in result.warnings:
                    messages.warning(request, warning)
            else:
                msg = (
                    f"案由数据初始化部分失败.新增 {result.created} 条,更新 {result.updated} 条,失败 {result.failed} 条."
                )
                messages.warning(request, msg)

                # 显示错误信息
                for error in result.errors[:5]:  # 最多显示 5 条错误
                    messages.error(request, error)

        except concurrent.futures.TimeoutError:
            messages.error(request, "初始化案由数据超时,请稍后重试")

        except Exception as e:
            logger.exception("初始化案由数据失败")
            messages.error(request, f"初始化案由数据失败: {e}")

        return HttpResponseRedirect(reverse("admin:core_causeofaction_changelist"))

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁用手动添加功能(数据应通过初始化导入)"""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: CauseOfAction | None = None) -> bool:
        """禁用删除功能(数据应通过初始化管理)"""
        return False
