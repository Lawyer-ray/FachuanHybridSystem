"""Agent 运行记录的 Django Admin。

律师全是普通用户、没有独立管理员角色，但律所负责人需要知道 AI 用量花在
哪、哪个模型贵。这里给一个只读视图（运行记录是审计数据，不该手工改）。
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import AgentApproval, AgentApprovalPolicy, AgentMemory, AgentRun, AgentSession


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    """成本与耗时（只读）。"""

    list_display = (
        "created_at",
        "user",
        "model",
        "status",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "duration_ms",
    )
    list_filter = ("status", "model", "created_at")
    search_fields = ("model", "user__username", "error_kind")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "session",
        "user",
        "model",
        "status",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "duration_ms",
        "error_kind",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[AgentRun]:
        return super().get_queryset(request).select_related("user", "session")


@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "llm_model", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "user__username")


@admin.register(AgentApproval)
class AgentApprovalAdmin(admin.ModelAdmin):
    """高危操作审批的审计视图。"""

    list_display = ("created_at", "tool_name", "status", "decided_by", "decided_at")
    list_filter = ("status", "created_at")
    search_fields = ("tool_name",)
    date_hierarchy = "created_at"


@admin.register(AgentApprovalPolicy)
class AgentApprovalPolicyAdmin(admin.ModelAdmin):
    """审批策略配置（P2-5）：用户 × 工具 → allow/ask/deny。"""

    list_display = ("user", "tool_pattern", "is_prefix", "action", "note", "updated_at")
    list_filter = ("action", "is_prefix")
    search_fields = ("tool_pattern", "user__username")
    ordering = ("-updated_at",)


@admin.register(AgentMemory)
class AgentMemoryAdmin(admin.ModelAdmin):
    """跨会话记忆（个人 / 团队 / 律所三级）。

    **策展不在这里做**：团队/律所层必须走 ``promote_memory``（强制改写 +
    PII 闸门），admin 直接改内容会绕过这两道闸门。所以内容字段只读，
    这里的作用是审计「谁记了什么、从哪次对话来的、有没有被提升」。
    """

    list_display = ("created_at", "scope", "kind", "status", "short_content", "hit_count", "created_by")
    list_filter = ("scope", "kind", "status", "created_at")
    search_fields = ("content", "created_by__username", "created_by__real_name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    autocomplete_fields: tuple[str, ...] = ()
    filter_horizontal = ("promoted_from",)
    readonly_fields = (
        "scope",
        "lawyer",
        "team",
        "law_firm",
        "kind",
        "content",
        "content_hash",
        "source_session",
        "promoted_from",
        "confidence",
        "hit_count",
        "last_hit_at",
        "created_by",
        "created_at",
        "updated_at",
    )

    @admin.display(description="内容")
    def short_content(self, obj: AgentMemory) -> str:
        return obj.content[:60] + ("…" if len(obj.content) > 60 else "")

    def get_queryset(self, request: HttpRequest) -> QuerySet[AgentMemory]:
        return super().get_queryset(request).select_related("lawyer", "team", "law_firm", "created_by")
