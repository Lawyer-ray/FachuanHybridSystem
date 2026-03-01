"""证据分组 Admin"""

from typing import Any, ClassVar

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import EvidenceGroup


@admin.register(EvidenceGroup)
class EvidenceGroupAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display: ClassVar = ("name", "case", "item_count", "sort_order", "created_at")
    list_filter: ClassVar = ("case",)
    search_fields: ClassVar = ("name", "case__name")
    autocomplete_fields: ClassVar = ("case",)
    filter_horizontal: ClassVar = ("items",)
    ordering: ClassVar = ["case", "sort_order"]

    @admin.display(description=_("证据数量"))
    def item_count(self, obj: EvidenceGroup) -> int:
        return obj.items.count()
