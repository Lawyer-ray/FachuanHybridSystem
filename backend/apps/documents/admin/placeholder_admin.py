"""
替换词 Admin 配置

Requirements: 6.1, 3.6
"""

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.documents.models import Placeholder


def _get_placeholder_usage_service() -> Any:
    from apps.documents.services.placeholder_usage_service import PlaceholderUsageService

    return PlaceholderUsageService()


def _get_code_placeholder_catalog_service() -> Any:
    from apps.documents.services.code_placeholder_catalog_service import CodePlaceholderCatalogService

    return CodePlaceholderCatalogService()


def _get_placeholder_admin_service() -> Any:
    from ..services import PlaceholderAdminService

    return PlaceholderAdminService()


class PlaceholderUsageFilter(admin.SimpleListFilter):
    title = _("用途")
    parameter_name: str = "usage"

    def lookups(self, request, model_admin) -> Any:
        return (
            ("contract", _("合同文件")),
            ("case", _("案件文件")),
            ("both", _("合同+案件")),
            ("unused", _("未使用")),
        )

    def queryset(self, request, queryset) -> Any:
        value = self.value()
        if not value:
            return queryset

        usage_map = getattr(self, "_usage_map_cache", None)
        if usage_map is None:
            usage_map = _get_placeholder_usage_service().get_usage_map()
            self._usage_map_cache = usage_map

        return _get_placeholder_admin_service().filter_by_usage(queryset, value, usage_map)


@admin.register(Placeholder)
class PlaceholderAdmin(admin.ModelAdmin):
    """
    替换词管理

    提供替换词的 CRUD 操作,支持搜索和过滤.
    """

    list_display: tuple[Any, ...] = (
        "key",
        "usage_display",
        "example_value_display",
        "is_active",
    )

    list_filter: tuple[Any, ...] = (
        "is_active",
        PlaceholderUsageFilter,
    )

    search_fields: tuple[Any, ...] = (
        "key",
        "display_name",
        "description",
    )

    ordering: tuple[Any, ...] = ("key",)

    fieldsets: tuple[Any, ...] = (
        (None, {"fields": ("key", "display_name")}),
        (_("示例和说明"), {"fields": ("example_value", "description")}),
        (_("状态"), {"fields": ("is_active",)}),
    )

    actions: ClassVar = ["activate_placeholders", "deactivate_placeholders"]

    def has_add_permission(self, request) -> Any:
        return False

    def _catalog_cache(self) -> Any:
        if not hasattr(self, "_cached_code_placeholder_catalog"):
            catalog = _get_code_placeholder_catalog_service()
            definitions = {d.key: d for d in catalog.list_definitions()}
            self._cached_code_placeholder_catalog = definitions
        return self._cached_code_placeholder_catalog

    def _usage_map_cache(self, request) -> Any:
        if request is not None and getattr(request, "_placeholder_usage_map_cached", None) is not None:
            return request._placeholder_usage_map_cached
        usage_map = _get_placeholder_usage_service().get_usage_map()
        if request is not None:
            request._placeholder_usage_map_cached = usage_map
        self._usage_map_for_changelist = usage_map
        return usage_map

    def _ensure_code_placeholders(self, request: Any) -> None:
        if getattr(request, "_code_placeholders_synced", False):
            return
        definitions = self._catalog_cache()
        service = _get_placeholder_admin_service()
        service.ensure_code_placeholders(definitions)
        request._code_placeholders_synced = True

    def get_queryset(self, request: Any) -> QuerySet[Any]:
        self._ensure_code_placeholders(request)
        self._usage_map_cache(request)
        qs = super().get_queryset(request)
        code_keys = list(self._catalog_cache().keys())
        service = _get_placeholder_admin_service()
        return service.get_filtered_queryset(qs, code_keys)

    def usage_display(self, obj) -> Any:
        usage_map = getattr(self, "_usage_map_for_changelist", None)
        if usage_map is None:
            usage_map = _get_placeholder_usage_service().get_usage_map()
        types = usage_map.get(obj.key, set()) or set()
        parts: list[Any] = []
        if "contract" in types:
            parts.append(str(_("合同文件")))
        if "case" in types:
            parts.append(str(_("案件文件")))
        if not parts:
            return format_html('<span style="color: #999;">{}</span>', "-")
        return " / ".join(parts)

    usage_display.short_description = _("用途")

    def code_service_display(self, obj) -> Any:
        definition = self._catalog_cache().get(obj.key)
        return definition.source if definition else ""

    code_service_display.short_description = _("来源服务")

    def code_category_display(self, obj) -> Any:
        definition = self._catalog_cache().get(obj.key)
        return definition.category if definition else ""

    code_category_display.short_description = _("分类")

    def example_value_display(self, obj) -> Any:
        """显示示例值"""
        if obj.example_value:
            # 截断过长的示例值
            value = obj.example_value
            if len(value) > 50:
                value = value[:50] + "..."
            return format_html(
                '<span title="{}" style="color: #666; font-style: italic;">{}</span>', obj.example_value, value
            )
        return format_html('<span style="color: #999;">{}</span>', "-")

    example_value_display.short_description = _("示例值")

    @admin.action(description=_("启用选中的替换词"))
    def activate_placeholders(self, request, queryset) -> None:
        """批量启用替换词"""
        updated = 0
        for placeholder in queryset:
            if not placeholder.is_active:
                placeholder.is_active = True
                placeholder.save(update_fields=["is_active"])
                updated += 1
        self.message_user(request, _("已启用 %(count)d 个替换词") % {"count": updated})

    @admin.action(description=_("禁用选中的替换词"))
    def deactivate_placeholders(self, request, queryset) -> None:
        """批量禁用替换词"""
        updated = 0
        for placeholder in queryset:
            if placeholder.is_active:
                placeholder.is_active = False
                placeholder.save(update_fields=["is_active"])
                updated += 1
        self.message_user(request, _("已禁用 %(count)d 个替换词") % {"count": updated})

    @admin.action(description=_("复制选中的替换词"))
    def duplicate_placeholders(self, request: Any, queryset: QuerySet[Any]) -> None:
        """复制替换词"""
        service = _get_placeholder_admin_service()
        count: int = 0
        for placeholder in queryset:
            service.duplicate_placeholder(placeholder)
            count += 1

        self.message_user(request, _("已复制 %(count)d 个替换词") % {"count": count})

    def get_readonly_fields(self, request, obj=None) -> Any:
        """编辑时 key 字段只读"""
        if obj:  # 编辑现有对象
            return ("key",)
        return ()
