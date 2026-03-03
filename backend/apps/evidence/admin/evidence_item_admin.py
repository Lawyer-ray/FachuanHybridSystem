"""证据明细独立 Admin（用于编辑三性说明、质证意见等详细字段）"""

from typing import Any, ClassVar

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import EvidenceItem


@admin.register(EvidenceItem)
class EvidenceItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display: ClassVar = (
        "order",
        "name",
        "evidence_type",
        "direction",
        "original_status",
        "page_count",
        "page_range_display",
        "evidence_list",
    )
    list_filter: ClassVar = ("direction", "evidence_type", "original_status", "evidence_list__case")
    search_fields: ClassVar = ("name", "purpose", "ocr_text")
    readonly_fields: ClassVar = ("file_hash", "page_count", "page_start", "page_end", "created_at", "updated_at")
    ordering: ClassVar = ["evidence_list", "order"]

    fieldsets: ClassVar = (
        (
            None,
            {
                "fields": ("evidence_list", "order", "name", "purpose"),
            },
        ),
        (
            _("证据属性"),
            {
                "fields": ("evidence_type", "direction", "original_status", "original_location"),
            },
        ),
        (
            _("三性说明"),
            {
                "fields": ("three_properties",),
                "description": _(
                    '格式: {"authenticity": {"opinion": "认可", "reason": "..."}, "legality": {...}, "relevance": {...}}'
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("质证意见"),
            {
                "fields": ("cross_examination",),
                "description": _("对方证据的质证意见，格式同三性说明"),
                "classes": ("collapse",),
            },
        ),
        (
            _("文件信息"),
            {
                "fields": ("file", "file_hash", "source_channel", "page_count", "page_start", "page_end"),
            },
        ),
        (
            _("OCR / AI"),
            {
                "fields": ("ocr_text", "ai_analysis"),
                "classes": ("collapse",),
            },
        ),
        (
            _("系统信息"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("页码"))
    def page_range_display(self, obj: EvidenceItem) -> str:
        return obj.page_range_display
