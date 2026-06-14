"""工作流 Django Admin"""

from __future__ import annotations

from django.contrib import admin

from apps.workflow.models import StepExecution, WorkflowRun, WorkflowTemplate


class StepExecutionInline(admin.TabularInline):
    model = StepExecution
    extra = 0
    readonly_fields = (
        "step_id", "step_name", "step_type", "status",
        "output_data", "error_message", "started_at", "finished_at",
    )
    can_delete = False


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "is_active")
    list_filter = ("category", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WorkflowRun)
class WorkflowRunAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "case", "status", "current_step_id", "started_at")
    list_select_related = ("template", "case")
    list_filter = ("status", "template")
    readonly_fields = ("temporal_workflow_id", "temporal_run_id")
    inlines = [StepExecutionInline]
