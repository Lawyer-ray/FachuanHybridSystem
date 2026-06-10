"""
补充协议 Admin 配置
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from apps.contracts.models import SupplementaryAgreement, SupplementaryAgreementParty


class SupplementaryAgreementPartyInline(admin.TabularInline[SupplementaryAgreementParty, SupplementaryAgreementParty]):  # pragma: no cover
    """补充协议当事人内联编辑"""

    model = SupplementaryAgreementParty
    extra = 1
    autocomplete_fields: ClassVar = ["client"]
    verbose_name = "当事人"
    verbose_name_plural = "当事人"

    def get_queryset(self, request: HttpRequest) -> QuerySet[SupplementaryAgreementParty, SupplementaryAgreementParty]:  # pragma: no cover
        return super().get_queryset(request).exclude(role="PRINCIPAL")

    class Media:  # pragma: no cover
        js = ("contracts/js/party_role_auto.js",)


@admin.register(SupplementaryAgreement)
class SupplementaryAgreementAdmin(admin.ModelAdmin):  # pragma: no cover
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

    @admin.display(description="当事人数量", ordering="party_count")
    def party_count(self, obj: SupplementaryAgreement) -> int:  # pragma: no cover
        """当事人数量（来自 annotate，无额外查询）"""
        return obj.party_count  # type: ignore[attr-defined,no-any-return]

    def get_queryset(self, request: HttpRequest) -> QuerySet[SupplementaryAgreement, SupplementaryAgreement]:  # pragma: no cover
        """优化查询：用 annotate(Count) 替代 prefetch_related + .count()，消除 N+1"""
        qs = super().get_queryset(request)
        return qs.select_related("contract").annotate(party_count=Count("parties"))  # type: ignore[no-any-return]
