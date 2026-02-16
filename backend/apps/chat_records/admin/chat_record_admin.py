"""Django admin configuration."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.chat_records.models import ChatRecordExportTask, ChatRecordProject, ChatRecordRecording, ChatRecordScreenshot


@admin.register(ChatRecordProject)
class ChatRecordProjectAdmin(admin.ModelAdmin):
    list_display: tuple[Any, ...] = ("id", "name", "created_by", "created_at", "workbench_link")
    search_fields: tuple[Any, ...] = ("name",)
    readonly_fields: tuple[Any, ...] = ("created_at", "updated_at")

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:project_id>/workbench/",
                self.admin_site.admin_view(self.workbench_view),
                name="chat_records_project_workbench",
            ),
        ]
        return custom_urls + urls

    def workbench_link(self, obj: ChatRecordProject) -> str:
        url = reverse("admin:chat_records_project_workbench", args=[obj.id])
        return mark_safe(f'<a href="{url}">进入工作台</a>')

    workbench_link.short_description = _("工作台")

    def workbench_view(self, request: HttpRequest, project_id: int) -> TemplateResponse:
        project = ChatRecordProject.objects.get(id=project_id)
        context = {
            "title": f"梳理聊天记录工作台:{project.name}",
            "project": project,
            "opts": self.model._meta,
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }
        return TemplateResponse(request, "admin/chat_records/workbench.html", context)


@admin.register(ChatRecordScreenshot)
class ChatRecordScreenshotAdmin(admin.ModelAdmin):
    list_display: tuple[Any, ...] = ("id", "project", "ordering", "title", "created_at")
    search_fields: tuple[Any, ...] = ("title", "note", "sha256")
    list_filter: tuple[Any, ...] = ("project",)
    readonly_fields: tuple[Any, ...] = ("created_at", "sha256")


@admin.register(ChatRecordExportTask)
class ChatRecordExportTaskAdmin(admin.ModelAdmin):
    list_display: tuple[Any, ...] = (
        "id",
        "project",
        "export_type",
        "status",
        "progress",
        "created_at",
        "download_link",
    )
    list_filter: tuple[Any, ...] = ("export_type", "status", "project")
    readonly_fields: tuple[Any, ...] = (
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "progress",
        "current",
        "total",
        "message",
        "error",
        "layout",
    )

    def download_link(self, obj: ChatRecordExportTask) -> str:
        if not obj.output_file:
            return "-"
        return mark_safe(f'<a href="/api/v1/chat-records/exports/{obj.id}/download">下载</a>')

    download_link.short_description = _("文件")


@admin.register(ChatRecordRecording)
class ChatRecordRecordingAdmin(admin.ModelAdmin):
    list_display: tuple[Any, ...] = (
        "id",
        "project",
        "original_name",
        "size_bytes",
        "duration_seconds",
        "extract_status",
        "extract_progress",
        "created_at",
    )
    list_filter: tuple[Any, ...] = ("project", "extract_status")
    search_fields: tuple[Any, ...] = ("original_name",)
    readonly_fields: tuple[Any, ...] = (
        "size_bytes",
        "duration_seconds",
        "extract_status",
        "extract_progress",
        "extract_current",
        "extract_total",
        "extract_message",
        "extract_error",
        "extract_started_at",
        "extract_finished_at",
        "created_at",
        "updated_at",
    )
