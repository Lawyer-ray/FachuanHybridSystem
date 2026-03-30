from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.pdf_splitting.models import PdfSplitJob, PdfSplittingTool


@admin.register(PdfSplittingTool)
class PdfSplittingToolAdmin(admin.ModelAdmin[PdfSplittingTool]):
    def changelist_view(  # type: ignore[override]
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "PDF 拆解",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/pdf_splitting/workbench.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: PdfSplittingTool | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: PdfSplittingTool | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}


@admin.register(PdfSplitJob)
class PdfSplitJobAdmin(admin.ModelAdmin[PdfSplitJob]):
    list_display = [
        "id",
        "status_display",
        "source_original_name",
        "source_type",
        "split_mode",
        "ocr_profile",
        "progress",
        "template_key",
        "created_by",
        "created_at",
    ]
    list_filter = ["status", "source_type", "split_mode", "ocr_profile", "template_key", "created_at"]
    search_fields = ["source_original_name", "source_abs_path", "id"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "source_type",
        "source_abs_path",
        "source_relpath",
        "source_original_name",
        "split_mode",
        "template_key",
        "template_version",
        "ocr_profile",
        "status",
        "total_pages",
        "processed_pages",
        "progress",
        "current_page",
        "task_id",
        "cancel_requested",
        "created_by",
        "summary_payload",
        "error_message",
        "export_zip_relpath",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ]
    change_form_template = "admin/pdf_splitting/pdfsplitjob/change_form.html"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def status_display(self, obj: PdfSplitJob) -> SafeString:
        color_map = {
            "pending": "#8d6e63",
            "processing": "#1565c0",
            "review_required": "#ef6c00",
            "exporting": "#5e35b1",
            "completed": "#2e7d32",
            "failed": "#c62828",
            "cancelled": "#546e7a",
        }
        color = color_map.get(obj.status, "#546e7a")
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.get_status_display())

    status_display.short_description = _("状态")  # type: ignore[attr-defined]

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        extra = extra_context or {}
        extra["pdf_split_job_id"] = object_id
        extra["pdf_split_status_api"] = f"/api/v1/pdf-splitting/jobs/{object_id}"
        extra["pdf_split_confirm_api"] = f"/api/v1/pdf-splitting/jobs/{object_id}/confirm"
        extra["pdf_split_cancel_api"] = f"/api/v1/pdf-splitting/jobs/{object_id}/cancel"
        extra["pdf_split_download_api"] = f"/api/v1/pdf-splitting/jobs/{object_id}/download"
        extra["pdf_split_preview_api_base"] = f"/api/v1/pdf-splitting/jobs/{object_id}/pages"
        extra["pdf_split_pdf_api"] = f"/api/v1/pdf-splitting/jobs/{object_id}/pdf"
        return super().change_view(request, object_id, form_url, extra_context=extra)
