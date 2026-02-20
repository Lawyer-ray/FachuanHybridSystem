from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseNumber


@admin.register(CaseNumber)
class CaseNumberAdmin(admin.ModelAdmin[CaseNumber]):
    list_display = ("id", "number", "case", "remarks", "created_at")
    list_filter = ("created_at",)
    search_fields = ("number", "remarks")
    raw_id_fields = ("case",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[CaseNumber, CaseNumber]:
        return super().get_queryset(request).select_related("case")

    fieldsets = (
        (None, {"fields": ("case", "number", "remarks")}),
        (_("时间信息"), {"fields": ("created_at",), "classes": ("collapse",)}),
    )
