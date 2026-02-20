"""Django admin configuration."""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.chat_records.models import ChatRecordExportTask, ChatRecordProject, ChatRecordRecording, ChatRecordScreenshot


@admin.register(ChatRecordProject)
class ChatRecordProjectAdmin(admin.ModelAdmin[ChatRecordProject]):
    list_display = ("id", "name", "created_by", "created_at", "workbench_link")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

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
        return format_html('<a href="{}">进入工作台</a>', url)

    workbench_link.short_description = _("工作台")  # type: ignore[attr-defined]

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
class ChatRecordScreenshotAdmin(admin.ModelAdmin[ChatRecordScreenshot]):
    list_display = ("id", "project", "ordering", "title", "created_at")
    search_fields = ("title", "note", "sha256")
    list_filter = ("project",)
    readonly_fields = ("created_at", "sha256")


@admin.register(ChatRecordExportTask)
class ChatRecordExportTaskAdmin(admin.ModelAdmin[ChatRecordExportTask]):
    list_display = (
        "id",
        "project",
        "export_type",
        "status",
        "progress",
        "created_at",
        "download_link",
    )
    list_filter = ("export_type", "status", "project")
    readonly_fields = (
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
        return format_html('<a href="/api/v1/chat-records/exports/{}/download">下载</a>', obj.id)

    download_link.short_description = _("文件")  # type: ignore[attr-defined]


@admin.register(ChatRecordRecording)
class ChatRecordRecordingAdmin(admin.ModelAdmin[ChatRecordRecording]):
    list_display = (
        "id",
        "project",
        "original_name",
        "size_bytes",
        "duration_seconds",
        "extract_status",
        "extract_progress",
        "created_at",
    )
    list_filter = ("project", "extract_status")
    search_fields = ("original_name",)
    readonly_fields = (
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
