"""证据分组 Admin"""

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet

from apps.evidence.models import EvidenceGroup


@admin.register(EvidenceGroup)
class EvidenceGroupAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display: ClassVar = ("name", "case", "item_count", "sort_order", "created_at")  # type: ignore[misc]
    list_filter: ClassVar = ("case",)
    search_fields: ClassVar = ("name", "case__name")
    autocomplete_fields: ClassVar = ("case",)
    filter_horizontal: ClassVar = ("items",)
    ordering: ClassVar = ["case", "sort_order"]

    def get_queryset(self, request: Any) -> QuerySet:  # pragma: no cover
        # 安全审计（2026-10-19）：列表行级案件过滤——非管理员仅可见本所指派/授权案件下的证据分组
        from apps.cases.admin.base_admin import apply_case_related_admin_access_filter

        qs = apply_case_related_admin_access_filter(request, super().get_queryset(request))
        return qs.annotate(item_count=Count("items"))  # type: ignore[no-any-return]

    @admin.display(description="证据数量")
    def item_count(self, obj: EvidenceGroup) -> int:  # pragma: no cover
        count: int | None = getattr(obj, "item_count", None)
        if count is None:
            count = obj.items.count()
        return count
