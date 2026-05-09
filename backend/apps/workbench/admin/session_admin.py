"""工作台 Django Admin 配置"""

from __future__ import annotations

from django.contrib import admin

from ..models import BatchJob, BatchJobItem, WorkbenchMessage, WorkbenchSession


@admin.register(WorkbenchSession)
class WorkbenchSessionAdmin(admin.ModelAdmin):
    list_display = ["session_id", "title", "user", "llm_model", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "session_id"]
    readonly_fields = ["session_id", "created_at", "updated_at"]
    raw_id_fields = ["user"]


@admin.register(WorkbenchMessage)
class WorkbenchMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "role", "tool_name", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["content", "tool_name"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["session"]


@admin.register(BatchJob)
class BatchJobAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "job_type", "status", "progress", "total_items", "completed_items", "failed_items", "created_at"]
    list_filter = ["status", "job_type", "created_at"]
    search_fields = ["prompt", "summary"]
    readonly_fields = ["id", "created_at", "updated_at", "started_at", "started_processing_at", "finished_at"]
    raw_id_fields = ["session"]


@admin.register(BatchJobItem)
class BatchJobItemAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "file_name", "status", "duration_ms", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["file_name", "result", "error"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["job"]
