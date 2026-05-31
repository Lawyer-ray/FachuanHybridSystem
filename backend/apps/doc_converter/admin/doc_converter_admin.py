from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from apps.doc_converter.models import DocConverterItem, DocConverterJob, DocConverterTool

class DocConverterItemInline(admin.TabularInline):
    model = DocConverterItem
    extra = 0
    readonly_fields = ("original_name", "status", "error", "duration_ms", "created_at")
    fields = ("original_name", "status", "error", "duration_ms")
    can_delete = False

@admin.register(DocConverterJob)
class DocConverterJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "total_files", "converted_files", "failed_files", "progress", "created_at")
    list_filter = ("status",)
    search_fields = ("id",)
    readonly_fields = (
        "id",
        "status",
        "total_files",
        "converted_files",
        "failed_files",
        "progress",
        "task_id",
        "output_zip",
        "error_message",
        "created_by",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )
    inlines = [DocConverterItemInline]

    def has_add_permission(self, request: object) -> bool:
        return False

@admin.register(DocConverterTool)
class DocConverterToolAdmin(admin.ModelAdmin):
    """DOC 转 DOCX 工作台"""

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "DOC 转 DOCX 工作台",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/doc_converter/workbench.html", context)

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
