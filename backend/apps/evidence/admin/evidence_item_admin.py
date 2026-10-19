"""证据明细独立 Admin（用于编辑三性说明、质证意见等详细字段）"""

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet

from apps.evidence.models import EvidenceItem, EvidenceItemProxy


@admin.register(EvidenceItemProxy)
class EvidenceItemAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display: ClassVar = (  # type: ignore[misc]
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
            "证据属性",
            {
                "fields": ("evidence_type", "direction", "original_status", "original_location"),
            },
        ),
        (
            "三性说明",
            {
                "fields": ("three_properties",),
                "classes": ("collapse",),
            },
        ),
        (
            "质证意见",
            {
                "fields": ("cross_examination",),
                "classes": ("collapse",),
            },
        ),
        (
            "文件信息",
            {
                "fields": ("file", "file_hash", "source_channel", "page_count", "page_start", "page_end"),
            },
        ),
        (
            "OCR / AI",
            {
                "fields": ("ocr_text", "ai_analysis"),
                "classes": ("collapse",),
            },
        ),
        (
            "系统信息",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request: Any) -> QuerySet:  # pragma: no cover
        # 安全审计（2026-10-19）：列表行级案件过滤——证据明细经 evidence_list→case 关联，
        # 非管理员仅可见本所指派/授权案件下的明细（口径同 CaseAdmin）
        from apps.evidence.admin.case_access import get_admin_accessible_case_queryset

        accessible_case_ids = get_admin_accessible_case_queryset(request).values("id")
        return super().get_queryset(request).filter(evidence_list__case_id__in=accessible_case_ids)

    @admin.display(description="页码")
    def page_range_display(self, obj: EvidenceItem) -> str:  # pragma: no cover
        return obj.page_range_display
