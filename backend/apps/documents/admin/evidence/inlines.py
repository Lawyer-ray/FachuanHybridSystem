"""Module for inlines."""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.documents.models import EvidenceItem


class EvidenceItemInline(admin.TabularInline[EvidenceItem, EvidenceItem]):
    model = EvidenceItem
    extra: int = 1
    fields: ClassVar[tuple[Any, ...]] = (
        "global_order_display",
        "name",
        "purpose",
        "file",
        "page_count",
        "page_range_display",
    )
    readonly_fields: ClassVar[tuple[Any, ...]] = ("global_order_display", "page_count", "page_range_display")
    ordering: list = ["order"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[EvidenceItem, EvidenceItem]:
        qs: QuerySet[EvidenceItem, EvidenceItem] = super().get_queryset(request)
        return qs

    @admin.display(description=_("序号"))
    def global_order_display(self, obj: EvidenceItem) -> Any:
        if not obj.pk:
            return "-"

        evidence_list = obj.evidence_list
        global_order = evidence_list.start_order + obj.order - 1
        return global_order

    @admin.display(description=_("页码范围"))
    def page_range_display(self, obj: EvidenceItem) -> Any:
        if obj.pk:
            return obj.page_range_display
        return "-"

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("documents/css/evidence_inline.css",)}
        js: ClassVar[tuple[str, ...]] = ("documents/js/evidence_sortable.js",)


__all__: list[str] = ["EvidenceItemInline"]
