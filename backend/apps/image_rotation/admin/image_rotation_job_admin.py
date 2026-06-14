from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.image_rotation.models import ImageRotationJob, ImageRotationPage


class ImageRotationPageInline(admin.TabularInline):  # pragma: no cover
    model = ImageRotationPage
    extra = 0
    can_delete = False
    readonly_fields = (
        "page_number",
        "original_filename",
        "detected_rotation",
        "onnx_rotation",
        "detection_confidence",
        "ocr_text",
        "suggested_filename",
        "source_type",
        "created_at",
    )
    fields = (
        "page_number",
        "original_filename",
        "detected_rotation",
        "onnx_rotation",
        "detection_confidence",
        "ocr_text",
        "suggested_filename",
    )


@admin.register(ImageRotationJob)
class ImageRotationJobAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display = ("id", "display_name", "status", "total_pages", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "name")
    readonly_fields = (
        "id",
        "name",
        "status",
        "total_pages",
        "export_zip_url",
        "export_pdf_url",
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = [ImageRotationPageInline]

    @admin.display(description="任务名称")
    def display_name(self, obj: ImageRotationJob) -> str:
        return obj.name or "未命名任务"

    def has_add_permission(self, request: object) -> bool:  # pragma: no cover
        return False
