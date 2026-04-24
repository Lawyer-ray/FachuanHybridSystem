"""
系统配置 Admin

提供 Django Admin 界面来管理系统配置项，包括飞书、钉钉等第三方服务配置。
"""

import os
from typing import Any, ClassVar, cast

from django.contrib import admin, messages
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec

from ._system_config_data import get_default_configs, get_env_mappings
from .forms import SystemConfigAdminForm


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin[SystemConfig]):
    """系统配置 Admin"""

    show_in_index = False  # 不在左侧菜单显示，通过右上角快捷入口访问

    form = SystemConfigAdminForm
    list_display = [
        "key",
        "category_display",
        "masked_value",
        "updated_at",
    ]
    list_filter = ["category", "is_secret"]
    search_fields = ["key", "description"]
    ordering = ["category", "key"]
    change_list_template = "admin/core/systemconfig/change_list.html"

    fieldsets = (
        (_("基本信息"), {"fields": ("key", "value", "category", "description")}),
        (_("安全设置"), {"fields": ("is_secret", "is_active"), "classes": ("collapse",)}),
        (_("时间信息"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields: ClassVar[list[str]] = ["created_at", "updated_at"]

    def category_display(self, obj: Any) -> Any:
        """显示分类标签"""
        colors = {
            "feishu": "#3370ff",
            "dingtalk": "#0089ff",
            "wechat_work": "#07c160",
            "telegram": "#0088cc",
            "court_sms": "#ff6b35",
            "ai": "#9c27b0",
            "llm": "#e91e63",
            "enterprise_data": "#0f766e",
            "scraper": "#ff9800",
            "ocr": "#009688",
            "general": "#607d8b",
        }
        color = colors.get(obj.category, "#607d8b")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px; white-space: nowrap;">{}</span>',
            color,
            obj.get_category_display(),
        )

    category_display.short_description = _("分类")  # type: ignore[attr-defined]
    category_display.admin_order_field = "category"  # type: ignore[attr-defined]

    def masked_value(self, obj: Any) -> Any:
        """显示脱敏后的值"""
        if not obj.value:
            return format_html('<span style="color: #999;">{}</span>', "未设置")

        if obj.is_secret:
            masked = self._mask_secret_value(obj.value)
            return format_html('<span style="font-family: monospace;">{}</span>', masked)
        else:
            if len(obj.value) > 50:
                return format_html('<span title="{}">{}</span>', obj.value, obj.value[:50] + "...")
            return obj.value

    masked_value.short_description = _("配置值")  # type: ignore[attr-defined]

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
            path(
                "trigger-update/",
                self.admin_site.admin_view(self.trigger_update_view),
                name="core_systemconfig_trigger_update",
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

    def save_model(self, request: Any, obj: SystemConfig, form: Any, change: bool) -> None:
        previous_key = ""
        if change and obj.pk:
            previous = SystemConfig.objects.filter(pk=obj.pk).only("key").first()
            previous_key = str(previous.key or "") if previous else ""
        super().save_model(request, obj, form, change)
        self._clear_config_cache(obj.key, previous_key=previous_key)

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
                stored_value = env_value
                if config_info.get("is_secret", False):
                    stored_value = SecretCodec().encrypt(env_value)
                SystemConfig.objects.update_or_create(
                    key=config_info["key"],
                    defaults={
                        "value": stored_value,
                        "category": config_info["category"],
                        "description": config_info["description"],
                        "is_secret": config_info.get("is_secret", False),
                    },
                )
                self._clear_config_cache(config_info["key"])
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

    def trigger_update_view(self, request: HttpRequest) -> HttpResponseRedirect:
        """触发系统更新任务。"""
        if request.method != "POST":
            messages.error(request, _("仅支持 POST 请求"))
            return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

        if not self.has_change_permission(request):
            messages.error(request, _("无权限执行系统更新"))
            return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

        raw_enable_post_update_setup = str(request.POST.get("enable_post_update_setup", "")).strip().lower()
        enable_post_update_setup = raw_enable_post_update_setup in {"1", "true", "on", "yes"}

        username = str(request.user.get_username() or request.user.pk or "")
        result = self._get_system_update_service().trigger_update(
            triggered_by=username,
            enable_post_update_setup=enable_post_update_setup,
        )
        if bool(result.get("accepted")):
            if enable_post_update_setup:
                messages.success(request, _("更新任务已提交，将自动执行 uv sync 与 migrate。"))
            else:
                messages.success(request, _("更新任务已提交，请稍后刷新查看状态"))
        else:
            message_text = str(result.get("message") or _("更新任务提交失败"))
            messages.warning(request, message_text)
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def _get_default_configs(self) -> list[dict[str, Any]]:
        """委托给模块级函数"""
        return get_default_configs()

    def _get_env_mappings(self) -> dict[str, dict[str, Any]]:
        """委托给模块级函数"""
        return get_env_mappings()

    def _mask_secret_value(self, value: str) -> str:
        plain_value = value
        codec = SecretCodec()
        if codec.is_encrypted(value):
            try:
                plain_value = codec.try_decrypt(value)
            except Exception:
                plain_value = value

        segments = [
            segment.strip()
            for segment in plain_value.replace(";", "\n").replace(",", "\n").splitlines()
            if segment.strip()
        ]
        if len(segments) > 1:
            return f"已配置 {len(segments)} 个值"

        target = segments[0] if segments else plain_value
        if len(target) > 8:
            return target[:4] + "*" * (len(target) - 8) + target[-4:]
        return "*" * len(target)

    @staticmethod
    def _clear_config_cache(key: str, *, previous_key: str = "") -> None:
        if previous_key and previous_key != key:
            cache.delete(f"system_config:{previous_key}")
        cache.delete(f"system_config:{key}")

    @staticmethod
    def _get_system_update_service() -> Any:
        from apps.core.dependencies import build_system_update_service

        return build_system_update_service()
