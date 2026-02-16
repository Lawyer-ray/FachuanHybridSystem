"""Module for inlines."""

from typing import Any, ClassVar

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.documents.models import EvidenceItem


class EvidenceItemInline(admin.TabularInline):
    model = EvidenceItem
    extra: int = 1
    fields: tuple[Any, ...] = (
        "global_order_display",
        "name",
        "purpose",
        "file",
        "page_count",
        "page_range_display",
    )
    readonly_fields: tuple[Any, ...] = ("global_order_display", "page_count", "page_range_display")
    ordering: ClassVar = ["order"]

    def get_queryset(self, request) -> None:
        qs = super().get_queryset(request)
        return qs

    def global_order_display(self, obj) -> None:
        if not obj.pk:
            return "-"

        evidence_list = obj.evidence_list
        global_order = evidence_list.start_order + obj.order - 1
        return global_order

    global_order_display.short_description = _("序号")

    def page_range_display(self, obj) -> None:
        if obj.pk:
            return obj.page_range_display
        return "-"

    page_range_display.short_description = _("页码范围")

    class Media:
        css: ClassVar = {"all": ("documents/css/evidence_inline.css",)}
        js: tuple[Any, ...] = ("documents/js/evidence_sortable.js",)


__all__: list[str] = ["EvidenceItemInline"]
