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
    # 安全审计：credentials 不进 search_fields——搜索词会进查询串/访问日志，泄露凭证片段
    search_fields = ("name", "provider_type")
    ordering = ("priority", "name")
    fieldsets = (
        ("基本信息", {"fields": ("name", "provider_type", "enabled", "priority")}),
        (
            "凭证配置",
            {
                "fields": ("credentials", "concurrency_per_key"),
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

    def get_changeform_initial_data(self, request: Any) -> dict[str, Any]:
        # 安全审计：credentials 是 EncryptedTextField，from_db_value 透明解密后会把明文凭证
        # 渲染进表单 HTML。编辑页不回填（留空=不修改），保存时空值保留库中原值。
        initial = super().get_changeform_initial_data(request)
        initial["credentials"] = ""
        return initial

    def get_form(self, request: Any, obj: Any = None, change: bool = False, **kwargs: Any) -> Any:
        form = super().get_form(request, obj, **kwargs)
        if "credentials" in form.base_fields:
            form.base_fields["credentials"].help_text = "留空表示不修改已保存的凭证"
        return form

    @admin.display(description="凭证数量")
    def credential_count(self, obj: DocumentParseProvider) -> int:
        return len(obj.parsed_credentials())

    def save_model(self, request: Any, obj: Any, form: Any, change: bool) -> None:
        # 安全审计：编辑时 credentials 留空 → 保留库中原值（get_prep_value 会重新加密）
        if change and not str(form.cleaned_data.get("credentials") or "").strip():
            old = DocumentParseProvider.objects.filter(pk=obj.pk).values_list("credentials", flat=True).first()
            if old:
                obj.credentials = old
        super().save_model(request, obj, form, change)
        ParseProviderService.invalidate_cache()

    def delete_model(self, request: Any, obj: Any) -> None:
        super().delete_model(request, obj)
        ParseProviderService.invalidate_cache()

    def delete_queryset(self, request: Any, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
        ParseProviderService.invalidate_cache()
