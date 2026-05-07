from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

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
    """虚拟 Admin，仅用于侧边栏入口"""

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        return redirect("admin:doc_converter_docconverterjob_changelist")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
