"""系统配置 Admin

提供 Django Admin 界面来管理系统配置项，包括飞书、钉钉等第三方服务配置。
"""

import logging
from typing import Any, ClassVar, cast

from django.contrib import admin, messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.core.security.secret_display import (
    SecretValueUndecryptable,
    describe_stored_value,
    mask_summary,
    reveal_stored_value,
)

from ._system_config_data import get_default_configs
from .forms import SystemConfigAdminForm

logger = logging.getLogger(__name__)


def _client_ip(request: HttpRequest) -> str:
    """取审计日志用的来源 IP（反代场景优先取 X-Forwarded-For 第一段）。"""
    forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR") or "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR") or "")


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):  # pragma: no cover
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
        ("基本信息", {"fields": ("key", "value", "stored_value_preview", "category", "description")}),
        ("安全设置", {"fields": ("is_secret", "is_active"), "classes": ("collapse",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields: ClassVar[list[str]] = ["stored_value_preview", "created_at", "updated_at"]

    def stored_value_preview(self, obj: Any) -> Any:  # pragma: no cover
        """编辑页常驻的「已存值」概览：敏感项只给掩码 + 计数，明文走另一个页面的显式动作。

        为什么不做成回填到输入框：回填明文等于把审计结论推翻（明文进 HTML / 进浏览器
        缓存）；回填掩码又会让人一提交就把掩码写进库。只读块两者都避开。
        """
        if obj is None or not obj.pk:
            return format_html('<span style="color:#999">{}</span>', "保存后这里显示已存值概览（敏感项只显示掩码）。")

        if not obj.is_secret:
            return format_html('<span style="color:#999">{}</span>', "非敏感项：明文就在上面的输入框里，无需另开页面。")

        desc = describe_stored_value(obj.value, is_secret=True)
        if desc.decrypt_failed:
            status = format_html('<span style="color:#b45309;font-weight:600">{}</span>', desc.failure_message)
        elif not desc.segment_count:
            status = format_html('<span style="color:#999">{}</span>', "未设置")
        else:
            status = format_html('<span style="color:#666">{}</span>', desc.summary)

        rows = format_html_join(
            "",
            '<div style="font-family:monospace;line-height:1.6">{}</div>',
            ((segment,) for segment in desc.segments),
        )
        link = format_html(
            '<div style="margin-top:8px"><a class="button" href="{}">查看已存值（需二次确认）</a></div>',
            reverse("admin:core_systemconfig_stored_value", args=[obj.pk]),
        )
        return format_html('<div>{}<div style="margin-top:6px">{}</div>{}</div>', status, rows, link)

    stored_value_preview.short_description = "已存值"  # type: ignore[attr-defined]

    def category_display(self, obj: Any) -> Any:  # pragma: no cover
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
            "email": "#2196f3",
            "cloud_storage": "#1565c0",
            "general": "#607d8b",
        }
        color = colors.get(obj.category, "#607d8b")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px; white-space: nowrap;">{}</span>',
            color,
            obj.get_category_display(),
        )

    category_display.short_description = "分类"  # type: ignore[attr-defined]
    category_display.admin_order_field = "category"  # type: ignore[attr-defined]

    def masked_value(self, obj: Any) -> Any:  # pragma: no cover
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

    masked_value.short_description = "配置值"  # type: ignore[attr-defined]

    def get_urls(self) -> list[Any]:  # pragma: no cover
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "init-defaults/",
                self.admin_site.admin_view(self.init_defaults_view),
                name="core_systemconfig_init_defaults",
            ),
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
            path(
                "<path:object_id>/stored-value/",
                self.admin_site.admin_view(self.stored_value_view),
                name="core_systemconfig_stored_value",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:  # pragma: no cover
        """自定义列表页面"""
        extra_context = extra_context or {}

        extra_context["show_init_button"] = True
        extra_context["show_clear_cache_button"] = True
        extra_context["has_add_permission"] = self.has_add_permission(request)

        # 按分类分组获取配置项
        from collections import defaultdict

        grouped_configs = defaultdict(list)
        for config in SystemConfig.objects.all().order_by("category", "key"):
            grouped_configs[config.category].append(config)

        # 构建分组数据
        category_labels = dict(SystemConfig.Category.choices)

        groups = []
        for category in SystemConfig.Category.values:
            configs = grouped_configs.get(category, [])
            if configs:
                groups.append(
                    {
                        "category": category,
                        "label": category_labels.get(category, category),
                        "count": len(configs),
                        "configs": configs,
                    }
                )

        extra_context["grouped_configs"] = groups
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request: Any, obj: SystemConfig, form: Any, change: bool) -> None:  # pragma: no cover
        previous_key = ""
        if change and obj.pk:
            previous = SystemConfig.objects.filter(pk=obj.pk).only("key").first()
            previous_key = str(previous.key or "") if previous else ""
        super().save_model(request, obj, form, change)
        self._clear_config_cache(obj.key, previous_key=previous_key)

    def init_defaults_view(self, request: Any) -> HttpResponseRedirect:  # pragma: no cover
        """初始化默认配置项（AI 服务由「AI 平台」管理页负责、文档解析由「解析平台」管理页负责，此处跳过）"""
        defaults = self._get_default_configs()
        created_count = 0

        for config in defaults:
            if config.get("category") in ("ai", "document_parsing"):
                continue
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

    def clear_cache_view(self, request: Any) -> HttpResponseRedirect:  # pragma: no cover
        """清除配置缓存"""
        cache.delete("system_config:all")
        for config in SystemConfig.objects.all():
            cache.delete(f"system_config:{config.key}")
        messages.success(request, "配置缓存已清除")
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def trigger_update_view(self, request: HttpRequest) -> HttpResponseRedirect:  # pragma: no cover
        """触发系统更新任务。"""
        if request.method != "POST":
            messages.error(request, "仅支持 POST 请求")
            return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

        if not self.has_change_permission(request):
            messages.error(request, "无权限执行系统更新")
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
                messages.success(request, "更新任务已提交，将自动执行 uv sync 与 migrate。")
            else:
                messages.success(request, "更新任务已提交，请稍后刷新查看状态")
        else:
            message_text = str(result.get("message") or "更新任务提交失败")
            messages.warning(request, message_text)
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def _get_default_configs(self) -> list[dict[str, Any]]:  # pragma: no cover
        """委托给模块级函数"""
        return get_default_configs()

    def _mask_secret_value(self, value: str) -> str:  # pragma: no cover
        """changelist 「配置值」列：委托给 security 层的统一掩码口径。"""
        return mask_summary(value)

    def stored_value_view(self, request: HttpRequest, object_id: str) -> Any:  # pragma: no cover
        """「已存值」页：默认只显示掩码；点「显示明文」才解密，且不缓存、记审计。

        - GET：掩码明细 + 二次确认按钮（页面上没有任何明文）
        - POST action=reveal：本次响应里带明文，响应头 no-store，刷新即消失
        - 权限：与编辑页同口径（has_change_permission），不另设门槛

        明文不入 session / 不入 messages（那会把密码写进缓存库）。
        """
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404(f"SystemConfig {object_id} 不存在")
        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        revealed = ""
        reveal_error = ""
        if request.method == "POST":
            if request.POST.get("action") != "reveal":
                return HttpResponseRedirect(request.get_full_path())
            try:
                revealed = reveal_stored_value(obj.value)
            except SecretValueUndecryptable as exc:
                reveal_error = str(exc)
            else:
                # 只记「谁在什么时候看了哪个配置」，绝不记明文
                logger.info(
                    "system_config.stored_value_revealed key=%s operator=%s client_ip=%s",
                    obj.key,
                    str(request.user.get_username()),
                    _client_ip(request),
                )

        context = {
            **self.admin_site.each_context(request),
            "title": f"已存值：{obj.key}",
            "opts": self.model._meta,
            "original": obj,
            "description": describe_stored_value(obj.value, is_secret=bool(obj.is_secret)),
            "revealed": revealed,
            "reveal_error": reveal_error,
            "change_url": reverse("admin:core_systemconfig_change", args=[obj.pk]),
        }
        response = TemplateResponse(request, "admin/core/systemconfig/stored_value.html", context)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response["Pragma"] = "no-cache"
        return response

    @staticmethod
    def _clear_config_cache(key: str, *, previous_key: str = "") -> None:  # pragma: no cover
        if previous_key and previous_key != key:
            cache.delete(f"system_config:{previous_key}")
        cache.delete(f"system_config:{key}")

    @staticmethod
    def _get_system_update_service() -> Any:  # pragma: no cover
        from apps.core.dependencies import build_system_update_service

        return build_system_update_service()
