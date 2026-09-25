"""AI 平台（LLMProvider）Admin 管理页。"""

import json
import logging
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.urls import path, reverse

from apps.core.models import LLMProvider
from apps.core.models.llm_provider import parse_key_entries
from apps.core.services.llm_provider_service import LLMProviderService

logger = logging.getLogger("apps.core.admin.llm_provider")

_PLACEHOLDERS: dict[str, str] = {
    "name": "如：律所 kimi",
    "base_url": "https://api.example.com/v1",
    "api_keys": "每行一个 Key；限模型的 Key 写成 sk-xxx|kimi-2.6,glm53",  # pragma: allowlist secret
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
    change_form_template = "admin/core/llmprovider/change_form.html"

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
                ),
                "description": (
                    "<b>API Keys</b>：每行一个 Key，可逐行声明该 Key 可用的模型；"
                    "留空表示网关免鉴权。不知道哪个 Key 支持哪些模型时，"
                    "用每行的「获取模型」按钮自动探测。"
                ),
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
            path(
                "<path:object_id>/fetch-models/",
                self.admin_site.admin_view(self.fetch_models_view),
                name="core_llmprovider_fetch_models",
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

    def fetch_models_view(self, request: HttpRequest, object_id: str) -> JsonResponse:
        """拉取远端模型列表（逐个 Key 探测网关授权模型），返回 JSON 供表单弹层渲染。"""
        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "仅支持 POST 请求"}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"ok": False, "error": "无权限执行该操作"}, status=403)

        try:
            raw_payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raw_payload = {}
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

        base_url, keys_raw = self._resolve_fetch_inputs(request, object_id, payload)
        if not base_url:
            return JsonResponse({"ok": False, "error": "请先填写 API 地址"}, status=400)

        api_keys = [key for key, _ in parse_key_entries(keys_raw)]
        result = LLMProviderService.fetch_remote_models(
            base_url,
            api_keys,
            probe_chat=self._parse_flag(payload.get("probe_chat"), default=True),
        )
        return JsonResponse(
            {
                "ok": result.ok,
                "url": result.url,
                "models": result.models,
                "common_models": result.common_models,
                "chat_models": result.chat_models,
                "per_key": [
                    {"index": item.index, "ok": item.ok, "models": item.models, "error": item.error}
                    for item in result.per_key
                ],
            }
        )

    @staticmethod
    def _parse_flag(raw: Any, *, default: bool) -> bool:
        """把前端传来的开关值解析为布尔；缺省或无法识别时取 ``default``。"""
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _resolve_fetch_inputs(self, request: HttpRequest, object_id: str, payload: dict[str, Any]) -> tuple[str, str]:
        """取探测用的 ``base_url`` / ``api_keys``：优先表单提交值，缺项回落库中已存值。"""
        base_url = str(payload.get("base_url") or "").strip()
        keys_raw = str(payload.get("api_keys") or "")
        if base_url and keys_raw:
            return base_url, keys_raw

        obj = self.get_object(request, object_id) if object_id else None
        if obj is None:
            return base_url, keys_raw
        saved = cast(LLMProvider, obj)
        return base_url or str(saved.base_url or "").strip(), keys_raw or str(saved.api_keys or "")

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)
        LLMProviderService.invalidate_cache()

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        super().delete_model(request, obj)
        LLMProviderService.invalidate_cache()

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
        LLMProviderService.invalidate_cache()
