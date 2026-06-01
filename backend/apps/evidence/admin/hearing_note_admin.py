"""庭审笔记 Admin"""

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet

from apps.evidence.models import HearingNote


@admin.register(HearingNote)
class HearingNoteAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("case", "content_short", "evidence_count", "created_at")  # type: ignore[misc]
    list_select_related = ("case",)
    list_filter: ClassVar = ("case",)
    search_fields: ClassVar = ("content", "case__name")
    autocomplete_fields: ClassVar = ("case",)
    filter_horizontal: ClassVar = ("evidence_items",)
    ordering: ClassVar = ["-created_at"]

    @admin.display(description="内容")
    def content_short(self, obj: HearingNote) -> str:
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    def get_queryset(self, request: Any) -> QuerySet[HearingNote]:
        return super().get_queryset(request).annotate(evidence_count=Count("evidence_items"))  # type: ignore[no-any-return]

    @admin.display(description="关联证据", ordering="evidence_count")
    def evidence_count(self, obj: HearingNote) -> int:
        return obj.evidence_count  # type: ignore[attr-defined,no-any-return]
