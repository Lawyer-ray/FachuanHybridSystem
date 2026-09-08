"""LLM 调用记录 Admin（只读审计视图）"""

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.core.models import LLMCallRecord


@admin.register(LLMCallRecord)
class LLMCallRecordAdmin(admin.ModelAdmin):  # pragma: no cover
    """LLM 调用记录：只读，用于用量与成本分析。"""

    list_display = ("id", "model", "backend", "caller", "success", "total_tokens", "duration_ms", "created_at")
    list_filter = ("backend", "success", "model")
    search_fields = ("model", "caller", "error_summary")
    readonly_fields = (
        "model",
        "backend",
        "caller",
        "success",
        "error_type",
        "error_summary",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "duration_ms",
        "created_at",
    )
    date_hierarchy = "created_at"
    list_per_page = 50

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[LLMCallRecord]:
        return super().get_queryset(request)
