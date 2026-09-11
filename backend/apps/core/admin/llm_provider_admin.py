"""AI 平台（LLMProvider）Admin 管理页。"""

import logging
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse

from apps.core.models import LLMProvider
from apps.core.services.llm_provider_service import LLMProviderService

logger = logging.getLogger("apps.core.admin.llm_provider")

_PLACEHOLDERS: dict[str, str] = {
    "name": "如：律所 kimi",
    "base_url": "https://api.example.com/v1",
    "api_keys": "每行一个 Key，留空免鉴权",  # pragma: allowlist secret
    "default_model": "如：kimi26",
    "extra_models": "逗号分隔，如：kimi26,kimi26-128k",
    "embedding_model": "留空不启用向量模型",
    "timeout": "如：120",
    "concurrency_per_key": "如：3",
    "priority": "数字越小越优先",
}


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """AI 平台配置：多平台、多 Key、每 Key 并发上限、模型路由。"""

    change_list_template = "admin/core/llmprovider/change_list.html"

    list_display = (
        "name",
        "base_url",
        "default_model",
        "priority",
        "concurrency_per_key",
        "key_count",
        "enabled",
        "updated_at",
    )
    list_filter = ("enabled",)
    search_fields = ("name", "base_url", "default_model", "api_keys")
    ordering = ("priority", "name")
    fieldsets = (
        ("基本信息", {"fields": ("name", "enabled", "priority")}),
        (
            "API 配置",
            {
                "fields": (
                    "base_url",
                    "api_keys",
                    "timeout",
                    "concurrency_per_key",
                )
            },
        ),
        ("模型配置", {"fields": ("default_model", "extra_models", "embedding_model")}),
    )

    def formfield_for_dbfield(self, db_field: models.Field, request: Any, **kwargs: Any) -> Any:
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is None:
            return field
        placeholder = _PLACEHOLDERS.get(db_field.name)
        if placeholder and isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
            field.widget.attrs["placeholder"] = placeholder
        return field

    @admin.display(description="Key 数量")
    def key_count(self, obj: LLMProvider) -> int:
        return len(obj.parsed_api_keys())

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom_urls = [
            path(
                "initialize-default/",
                self.admin_site.admin_view(self.initialize_default_view),
                name="core_llmprovider_initialize_default",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:
        extra_context = extra_context or {}
        extra_context["show_initialize_button"] = True
        return super().changelist_view(request, extra_context=extra_context)

    def initialize_default_view(self, request: HttpRequest) -> HttpResponseRedirect:
        """初始化基础 AI 平台数据（幂等：表为空时写入一条默认平台）。"""
        if request.method != "POST":
            messages.error(request, "仅支持 POST 请求")
            return HttpResponseRedirect(reverse("admin:core_llmprovider_changelist"))
        if not self.has_add_permission(request) or not self.has_change_permission(request):
            messages.error(request, "无权限执行初始化")
            return HttpResponseRedirect(reverse("admin:core_llmprovider_changelist"))
        try:
            created, skipped = LLMProviderService.initialize_default()
        except Exception as exc:
            logger.exception("初始化 AI 服务失败")
            messages.error(request, f"初始化失败：{exc}")
        else:
            if created:
                messages.success(request, "AI 平台初始化成功，已写入基础平台配置")
            else:
                messages.info(request, "已存在平台配置，跳过初始化（不覆盖已有数据）")
        return HttpResponseRedirect(reverse("admin:core_llmprovider_changelist"))

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)
        LLMProviderService.invalidate_cache()

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        super().delete_model(request, obj)
        LLMProviderService.invalidate_cache()

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
        LLMProviderService.invalidate_cache()
