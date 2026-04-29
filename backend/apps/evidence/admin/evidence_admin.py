"""Django admin configuration."""

import logging
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import EvidenceList

from .evidence import EvidenceItemInline, EvidenceListForm
from .evidence.mixins import EvidenceListAdminActionsMixin, EvidenceListAdminSaveMixin, EvidenceListAdminViewsMixin
from .hearing_mode import HearingModeAdminMixin

logger = logging.getLogger(__name__)


@admin.register(EvidenceList)
class EvidenceListAdmin(
    HearingModeAdminMixin,
    EvidenceListAdminViewsMixin,
    EvidenceListAdminActionsMixin,
    EvidenceListAdminSaveMixin,
    admin.ModelAdmin,
):
    form = EvidenceListForm

    list_display: tuple[Any, ...] = (
        "title",
        "case_display",
        "list_type",
        "item_count_display",
        "order_range_display",
        "total_pages_display",
        "page_range_display",
        "export_version",
        "has_merged_pdf_display",
        "actions_display",
        "hearing_mode_link",
        "updated_at",
    )

    list_filter: tuple[Any, ...] = ("case", "list_type")
    search_fields: tuple[Any, ...] = ("title", "case__name")
    ordering: ClassVar = ["case", "order"]
    autocomplete_fields: tuple[Any, ...] = ("export_template",)

    readonly_fields: tuple[Any, ...] = (
        "list_type",
        "order",
        "page_range_display",
        "order_range_display",
        "total_pages",
        "merged_pdf",
        "created_by",
        "created_at",
        "updated_at",
    )

    fieldsets: tuple[Any, ...] = (
        (None, {"fields": ("case",)}),
        (
            _("自动计算信息"),
            {
                "fields": ("list_type", "order_range_display", "total_pages", "page_range_display"),
                "description": _("以下信息由系统自动计算,无需手动填写."),
            },
        ),
        (
            _("合并PDF"),
            {
                "fields": ("merged_pdf",),
                "description": _("点击列表页的「合并」按钮将证据文件合并为PDF."),
            },
        ),
        (
            _("导出设置"),
            {
                "fields": ("export_version", "export_template"),
                "description": _("导出版本号用于文件名控制,请手动修改.选择导出模板后,导出清单时将使用该模板格式."),
                "classes": ("evidence-export-section",),
            },
        ),
        (
            _("系统信息"),
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines: ClassVar = [EvidenceItemInline]
    actions: ClassVar = ["merge_pdfs", "export_list_word", "export_list_zip"]
    list_select_related: tuple[Any, ...] = ("case", "created_by")

    def get_queryset(self, request: Any) -> QuerySet:
        return super().get_queryset(request).annotate(item_count=Count("items"))

    @admin.display(description=_("开庭"))
    def hearing_mode_link(self, obj: EvidenceList) -> str:
        url = reverse("admin:evidence_hearing_mode", args=[obj.case_id])
        return format_html('<a class="button" href="{}" target="_blank">⚖️</a>', url)

    class Media:
        css: ClassVar = {"all": ("evidence/css/evidence_admin.css",)}
        js: tuple[Any, ...] = (
            "evidence/js/evidence_sortable.js",
            "evidence/js/evidence_merge.js",
            "evidence/js/evidence_list_type.js",
        )
