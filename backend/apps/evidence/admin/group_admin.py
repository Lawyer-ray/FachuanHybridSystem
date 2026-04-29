"""证据分组 Admin"""

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import EvidenceGroup


@admin.register(EvidenceGroup)
class EvidenceGroupAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "case", "item_count", "sort_order", "created_at")  # type: ignore[misc]
    list_filter: ClassVar = ("case",)
    search_fields: ClassVar = ("name", "case__name")
    autocomplete_fields: ClassVar = ("case",)
    filter_horizontal: ClassVar = ("items",)
    ordering: ClassVar = ["case", "sort_order"]

    def get_queryset(self, request: Any) -> QuerySet:
        return super().get_queryset(request).annotate(item_count=Count("items"))  # type: ignore[no-any-return]

    @admin.display(description=_("证据数量"))
    def item_count(self, obj: EvidenceGroup) -> int:
        count: int | None = getattr(obj, "item_count", None)
        if count is None:
            count = obj.items.count()
        return count
