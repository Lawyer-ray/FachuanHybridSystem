"""AI 平台（LLMProvider）Admin 管理页。"""

from typing import Any

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.core.models import LLMProvider
from apps.core.services.llm_provider_service import LLMProviderService

_PLACEHOLDERS: dict[str, str] = {
    "name": "如：律所 kimi",
    "base_url": "https://api.example.com/v1",
    "api_keys": "每行一个 Key，留空免鉴权",  # pragma: allowlist secret
    "default_model": "如：kimi26",
    "extra_models": "逗号分隔，如：kimi26,kimi26-128k",
    "embedding_model": "留空沿用默认模型",
    "timeout": "如：120",
    "concurrency_per_key": "0 表示不限制",
    "priority": "数字越小越优先",
}


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """AI 平台配置：多平台、多 Key、每 Key 并发上限、模型路由。"""

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
    list_editable = ("enabled", "priority")
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
        placeholder = _PLACEHOLDERS.get(db_field.name)
        if placeholder and isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
            field.widget.attrs["placeholder"] = placeholder
        return field

    @admin.display(description="Key 数量")
    def key_count(self, obj: LLMProvider) -> int:
        return len(obj.parsed_api_keys())

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)
        LLMProviderService.invalidate_cache()

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        super().delete_model(request, obj)
        LLMProviderService.invalidate_cache()

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
        LLMProviderService.invalidate_cache()
