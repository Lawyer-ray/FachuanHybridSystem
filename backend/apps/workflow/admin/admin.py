"""工作流 Django Admin"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.workflow.models import StepExecution, WorkflowRun, WorkflowTemplate


class StepExecutionInline(admin.TabularInline):
    model = StepExecution
    extra = 0
    readonly_fields = (
        "step_id",
        "step_name",
        "step_type",
        "status",
        "output_data",
        "error_message",
        "started_at",
        "finished_at",
    )
    can_delete = False


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request: Any, obj: Any = None) -> tuple[str, ...]:
        # 安全审计 A-01 旁路：steps_schema 含 code/http/mcp_tool 执行能力，
        # 非 superuser 一律只读，防经 Django admin 绕过 API 白名单。
        base = tuple(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return base
        return base + ("steps_schema",)

    list_display = ("name", "slug", "category", "is_active")
    list_filter = ("category", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WorkflowRun)
class WorkflowRunAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "case", "status", "current_step_id", "started_at")
    list_filter = ("status", "template")
    readonly_fields = ("temporal_workflow_id", "temporal_run_id")
    inlines = [StepExecutionInline]
