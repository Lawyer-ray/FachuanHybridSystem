from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.cases.models import CaseAssignment


@admin.register(CaseAssignment)
class CaseAssignmentAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display = ("id", "case", "lawyer")
    list_select_related = ("case", "lawyer")
    list_per_page = 50
    search_fields = ("case__name", "lawyer__real_name")

    def get_queryset(self, request: HttpRequest) -> QuerySet[CaseAssignment, CaseAssignment]:  # pragma: no cover
        """行级过滤：仅保留可访问案件下的指派记录（is_admin 全量）。"""
        from apps.cases.admin.base_admin import apply_case_related_admin_access_filter

        return apply_case_related_admin_access_filter(request, super().get_queryset(request))  # type: ignore[no-any-return]
