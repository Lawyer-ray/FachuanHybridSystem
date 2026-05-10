from __future__ import annotations

from django.contrib import admin

from apps.cases.models import CaseAssignment


@admin.register(CaseAssignment)
class CaseAssignmentAdmin(admin.ModelAdmin[CaseAssignment]):
    list_display = ("id", "case", "lawyer")
    list_select_related = ("case", "lawyer")
    list_per_page = 50
    search_fields = ("case__name", "lawyer__real_name")
