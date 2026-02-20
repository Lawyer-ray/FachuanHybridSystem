"""
替换词 Admin 配置

Requirements: 6.1, 3.6
"""

from typing import Any, ClassVar

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.documents.models import Placeholder
from apps.documents.services.code_placeholder_catalog_service import CodePlaceholderCatalogService
from apps.documents.services.placeholder_usage_service import PlaceholderUsageService


class PlaceholderUsageFilter(admin.SimpleListFilter):
    title = _("用途")
    parameter_name: str = "usage"

    def lookups(self, request, model_admin) -> None:
        return (
            ("contract", _("合同文件")),
            ("case", _("案件文件")),
            ("both", _("合同+案件")),
            ("unused", _("未使用")),
        )

    def queryset(self, request, queryset) -> None:
        value = self.value()
        if not value:
            return queryset

        usage_map = getattr(self, "_usage_map_cache", None)
        if usage_map is None:
            usage_map = PlaceholderUsageService().get_usage_map()
            self._usage_map_cache = usage_map

        contract_only = {k for k, v in usage_map.items() if v == {"contract"}}
        case_only = {k for k, v in usage_map.items() if v == {"case"}}
        both = {k for k, v in usage_map.items() if {"contract", "case"}.issubset(v)}
        used = set(usage_map.keys())

        if value == "contract":
            return queryset.filter(key__in=contract_only)
        if value == "case":
            return queryset.filter(key__in=case_only)
        if value == "both":
            return queryset.filter(key__in=both)
        if value == "unused":
            return queryset.exclude(key__in=used)
        return queryset


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

    def has_add_permission(self, request) -> None:
        return False

    def _catalog_cache(self) -> None:
        if not hasattr(self, "_cached_code_placeholder_catalog"):
            catalog = CodePlaceholderCatalogService()
            definitions = {d.key: d for d in catalog.list_definitions()}
            self._cached_code_placeholder_catalog = definitions
        return self._cached_code_placeholder_catalog

    def _usage_map_cache(self, request) -> None:
        if request is not None and getattr(request, "_placeholder_usage_map_cached", None) is not None:
            return request._placeholder_usage_map_cached
        usage_map = PlaceholderUsageService().get_usage_map()
        if request is not None:
            request._placeholder_usage_map_cached = usage_map
        self._usage_map_for_changelist = usage_map
        return usage_map

    def _ensure_code_placeholders(self, request) -> None:
        if getattr(request, "_code_placeholders_synced", False):
            return
        definitions = self._catalog_cache()
        existing_keys = set(Placeholder.objects.values_list("key", flat=True))
        to_create: list[Any] = []
        for key, definition in definitions.items():
            if key in existing_keys:
                continue
            to_create.append(
                Placeholder(
                    key=key,
                    display_name=definition.display_name or key,
                    example_value=definition.example_value or "",
                    description=definition.description or "",
                    is_active=True,
                )
            )
        if to_create:
            Placeholder.objects.bulk_create(to_create, ignore_conflicts=True)
        request._code_placeholders_synced = True

    def get_queryset(self, request) -> None:
        self._ensure_code_placeholders(request)
        self._usage_map_cache(request)
        qs = super().get_queryset(request)
        code_keys = list(self._catalog_cache().keys())
        return qs.filter(key__in=code_keys)

    def usage_display(self, obj) -> None:
        usage_map = getattr(self, "_usage_map_for_changelist", None)
        if usage_map is None:
            usage_map = PlaceholderUsageService().get_usage_map()
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

    def code_service_display(self, obj) -> None:
        definition = self._catalog_cache().get(obj.key)
        return definition.source if definition else ""

    code_service_display.short_description = _("来源服务")

    def code_category_display(self, obj) -> Any:
        definition = self._catalog_cache().get(obj.key)
        return definition.category if definition else ""

    code_category_display.short_description = _("分类")

    def example_value_display(self, obj) -> None:
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
        self.message_user(request, _(f"已启用 {updated} 个替换词"))

    @admin.action(description=_("禁用选中的替换词"))
    def deactivate_placeholders(self, request, queryset) -> None:
        """批量禁用替换词"""
        updated = 0
        for placeholder in queryset:
            if placeholder.is_active:
                placeholder.is_active = False
                placeholder.save(update_fields=["is_active"])
                updated += 1
        self.message_user(request, _(f"已禁用 {updated} 个替换词"))

    @admin.action(description=_("复制选中的替换词"))
    def duplicate_placeholders(self, request, queryset) -> None:
        """复制替换词"""
        count = 0
        for placeholder in queryset:
            # 生成新的 key
            new_key = f"{placeholder.key}_copy"
            suffix = 1
            while Placeholder.objects.filter(key=new_key).exists():
                new_key = f"{placeholder.key}_copy_{suffix}"
                suffix += 1

            # 创建副本
            Placeholder.objects.create(
                key=new_key,
                display_name=f"{placeholder.display_name} (副本)",
                example_value=placeholder.example_value,
                description=placeholder.description,
                is_active=False,  # 副本默认禁用
            )
            count += 1

        self.message_user(request, _(f"已复制 {count} 个替换词"))

    def get_readonly_fields(self, request, obj=None) -> None:
        """编辑时 key 字段只读"""
        if obj:  # 编辑现有对象
            return ("key",)
        return ()
