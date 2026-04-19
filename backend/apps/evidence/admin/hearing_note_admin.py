"""庭审笔记 Admin"""

from typing import Any, ClassVar

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import HearingNote


@admin.register(HearingNote)
class HearingNoteAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("case", "content_short", "evidence_count", "created_at")
    list_filter: ClassVar = ("case",)
    search_fields: ClassVar = ("content", "case__name")
    autocomplete_fields: ClassVar = ("case",)
    filter_horizontal: ClassVar = ("evidence_items",)
    ordering: ClassVar = ["-created_at"]

    @admin.display(description=_("内容"))
    def content_short(self, obj: HearingNote) -> str:
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    @admin.display(description=_("关联证据"))
    def evidence_count(self, obj: HearingNote) -> int:
        return obj.evidence_items.count()
