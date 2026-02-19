"""
系统配置 Admin

提供 Django Admin 界面来管理系统配置项，包括飞书、钉钉等第三方服务配置。
"""

import os
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.models import SystemConfig

from ._system_config_data import get_default_configs, get_env_mappings


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    """系统配置 Admin"""

    list_display: ClassVar[list[str]] = [
        "key",
        "category_display",
        "masked_value",
        "is_secret",
        "is_active",
        "updated_at",
    ]
    list_filter: ClassVar[list[str]] = ["category", "is_secret", "is_active"]
    search_fields: ClassVar[list[str]] = ["key", "description"]
    list_editable: ClassVar[list[str]] = ["is_active"]
    ordering: ClassVar[list[str]] = ["category", "key"]

    fieldsets = (
        ("基本信息", {"fields": ("key", "value", "category", "description")}),
        ("安全设置", {"fields": ("is_secret", "is_active"), "classes": ("collapse",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields: ClassVar[list[str]] = ["created_at", "updated_at"]

    def category_display(self, obj: Any) -> Any:
        """显示分类标签"""
        colors = {
            "feishu": "#3370ff",
            "dingtalk": "#0089ff",
            "wechat_work": "#07c160",
            "court_sms": "#ff6b35",
            "ai": "#9c27b0",
            "scraper": "#ff9800",
            "general": "#607d8b",
        }
        color = colors.get(obj.category, "#607d8b")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px;">{}</span>',
            color,
            obj.get_category_display(),
        )

    category_display.short_description = "分类"  # type: ignore[attr-defined]
    category_display.admin_order_field = "category"  # type: ignore[attr-defined]

    def masked_value(self, obj: Any) -> Any:
        """显示脱敏后的值"""
        if not obj.value:
            return format_html('<span style="color: #999;">未设置</span>')

        if obj.is_secret:
            if len(obj.value) > 8:
                masked = obj.value[:4] + "*" * (len(obj.value) - 8) + obj.value[-4:]
            else:
                masked = "*" * len(obj.value)
            return format_html('<span style="font-family: monospace;">{}</span>', masked)
        else:
            if len(obj.value) > 50:
                return format_html('<span title="{}">{}</span>', obj.value, obj.value[:50] + "...")
            return obj.value

    masked_value.short_description = "配置值"  # type: ignore[attr-defined]

    def get_urls(self) -> list[Any]:
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "init-defaults/",
                self.admin_site.admin_view(self.init_defaults_view),
                name="core_systemconfig_init_defaults",
            ),
            path("sync-env/", self.admin_site.admin_view(self.sync_env_view), name="core_systemconfig_sync_env"),
            path(
                "clear-cache/",
                self.admin_site.admin_view(self.clear_cache_view),
                name="core_systemconfig_clear_cache",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:
        """自定义列表页面"""
        extra_context = extra_context or {}
        extra_context["show_init_button"] = True
        extra_context["show_sync_button"] = True
        extra_context["show_clear_cache_button"] = True
        extra_context["has_add_permission"] = self.has_add_permission(request)
        return super().changelist_view(request, extra_context=extra_context)

    def init_defaults_view(self, request: Any) -> HttpResponseRedirect:
        """初始化默认配置项"""
        defaults = self._get_default_configs()
        created_count = 0

        for config in defaults:
            _, created = SystemConfig.objects.get_or_create(
                key=config["key"],
                defaults={
                    "value": config.get("value", ""),
                    "category": config["category"],
                    "description": config["description"],
                    "is_secret": config.get("is_secret", False),
                },
            )
            if created:
                created_count += 1

        if created_count > 0:
            messages.success(request, f"成功创建 {created_count} 个默认配置项")
        else:
            messages.info(request, "所有默认配置项已存在")

        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def sync_env_view(self, request: Any) -> HttpResponseRedirect:
        """从环境变量同步配置"""
        env_mappings = self._get_env_mappings()
        synced_count = 0

        for env_key, config_info in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value:
                SystemConfig.objects.update_or_create(
                    key=config_info["key"],
                    defaults={
                        "value": env_value,
                        "category": config_info["category"],
                        "description": config_info["description"],
                        "is_secret": config_info.get("is_secret", False),
                    },
                )
                synced_count += 1

        if synced_count > 0:
            messages.success(request, f"成功从环境变量同步 {synced_count} 个配置项")
        else:
            messages.info(request, "没有找到可同步的环境变量")

        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def clear_cache_view(self, request: Any) -> HttpResponseRedirect:
        """清除配置缓存"""
        cache.delete("system_config:all")
        for config in SystemConfig.objects.all():
            cache.delete(f"system_config:{config.key}")
        messages.success(request, "配置缓存已清除")
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def _get_default_configs(self) -> list[dict[str, Any]]:
        """委托给模块级函数"""
        return get_default_configs()

    def _get_env_mappings(self) -> dict[str, dict[str, Any]]:
        """委托给模块级函数"""
        return get_env_mappings()
