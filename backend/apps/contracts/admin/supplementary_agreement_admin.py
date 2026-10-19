"""
补充协议 Admin 配置
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from apps.contracts.models import SupplementaryAgreement, SupplementaryAgreementParty


class SupplementaryAgreementPartyInline(
    admin.TabularInline[SupplementaryAgreementParty, SupplementaryAgreementParty]
):  # pragma: no cover
    """补充协议当事人内联编辑"""

    model = SupplementaryAgreementParty
    extra = 1
    autocomplete_fields: ClassVar = ["client"]
    verbose_name = "当事人"
    verbose_name_plural = "当事人"

    def get_queryset(
        self, request: HttpRequest
    ) -> QuerySet[SupplementaryAgreementParty, SupplementaryAgreementParty]:  # pragma: no cover
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

    def get_queryset(
        self, request: HttpRequest
    ) -> QuerySet[SupplementaryAgreement, SupplementaryAgreement]:  # pragma: no cover
        """行级过滤 + 优化查询：用 annotate(Count) 替代 prefetch_related + .count()，消除 N+1"""
        from apps.contracts.admin.access import apply_contract_related_admin_access_filter

        qs = super().get_queryset(request)
        qs = apply_contract_related_admin_access_filter(request, qs)
        return qs.select_related("contract").annotate(party_count=Count("parties"))  # type: ignore[no-any-return]

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # pragma: no cover
        """安全审计（2026-10-19）：contract FK 可选项按行级口径过滤（同 get_queryset），
        防止受限用户通过表单把补充协议挂到他人合同下（跨合同越权写入）。"""
        if db_field.name == "contract":
            from apps.contracts.admin.access import get_admin_accessible_contract_queryset

            kwargs["queryset"] = get_admin_accessible_contract_queryset(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(
        self, request: HttpRequest, obj: SupplementaryAgreement, form: Any, change: bool
    ) -> None:  # pragma: no cover
        """保存前对 obj.contract 做行级二次校验（安全审计 2026-10-19，
        防表单可选项被绕过 / 陈旧选项写入他人合同）。"""
        from apps.contracts.admin.access import ensure_admin_contract_access

        if obj.contract_id:
            ensure_admin_contract_access(request, obj.contract_id)
        super().save_model(request, obj, form, change)
