"""解析平台（DocumentParseProvider）Admin 管理页。"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.db import models

from apps.core.models import DocumentParseProvider
from apps.core.services.document_parse_provider_service import ParseProviderService

_PLACEHOLDERS: dict[str, str] = {
    "name": "如：律所 MinerU",
    "credentials": "每行一个，TextinParse: app_id|secret_code；MinerU: 一行一个 API Key",  # pragma: allowlist secret
    "concurrency_per_key": "如：3",
    "priority": "数字越小越优先",
}


@admin.register(DocumentParseProvider)
class DocumentParseProviderAdmin(admin.ModelAdmin):
    """解析平台配置：多平台、多凭证、每凭证并发上限、按优先级自动选择。"""

    list_display = (
        "name",
        "provider_type",
        "priority",
        "concurrency_per_key",
        "credential_count",
        "enabled",
        "updated_at",
    )
    list_filter = ("enabled", "provider_type")
    search_fields = ("name", "provider_type", "credentials")
    ordering = ("priority", "name")
    fieldsets = (
        ("基本信息", {"fields": ("name", "provider_type", "enabled", "priority")}),
        (
            "凭证配置",
            {
                "fields": ("credentials", "concurrency_per_key"),
                "description": (
                    "TextinParse：每行一个凭证对，格式 <code>app_id|secret_code</code>（管道符分隔），"
                    "多行即可实现多凭证并发；MinerU：每行一个 API Key。"
                ),
            },
        ),
    )

    def formfield_for_dbfield(self, db_field: models.Field, request: Any, **kwargs: Any) -> Any:
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is None:
            return field
        placeholder = _PLACEHOLDERS.get(db_field.name)
        if placeholder and isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
            field.widget.attrs["placeholder"] = placeholder
        return field

    @admin.display(description="凭证数量")
    def credential_count(self, obj: DocumentParseProvider) -> int:
        return len(obj.parsed_credentials())

    def save_model(self, request: Any, obj: Any, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)
        ParseProviderService.invalidate_cache()

    def delete_model(self, request: Any, obj: Any) -> None:
        super().delete_model(request, obj)
        ParseProviderService.invalidate_cache()

    def delete_queryset(self, request: Any, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
        ParseProviderService.invalidate_cache()
