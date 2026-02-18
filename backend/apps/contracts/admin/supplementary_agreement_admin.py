"""
补充协议 Admin 配置
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.contracts.models import SupplementaryAgreement, SupplementaryAgreementParty


class SupplementaryAgreementPartyInline(admin.TabularInline):
    """补充协议当事人内联编辑"""

    model = SupplementaryAgreementParty
    extra = 1
    autocomplete_fields: ClassVar = ["client"]
    verbose_name = "当事人"
    verbose_name_plural = "当事人"


@admin.register(SupplementaryAgreement)
class SupplementaryAgreementAdmin(admin.ModelAdmin[SupplementaryAgreement]):
    """补充协议 Admin"""

    list_display = (
        "id",
        "name",
        "contract",
        "party_count",
        "created_at",
        "updated_at",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = ("name", "contract__name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields: ClassVar = ["contract"]

    inlines: ClassVar = [SupplementaryAgreementPartyInline]

    fieldsets = (
        ("基本信息", {"fields": ("contract", "name")}),
        (
            "时间信息",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def party_count(self, obj: SupplementaryAgreement) -> int:
        """当事人数量"""
        return obj.parties.count()

    party_count.short_description = "当事人数量"  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[SupplementaryAgreement, SupplementaryAgreement]:
        """优化查询"""
        qs = super().get_queryset(request)
        return qs.select_related("contract").prefetch_related("parties")
