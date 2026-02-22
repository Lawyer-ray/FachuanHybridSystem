from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.contracts.admin.mixins.action_mixin import ContractActionMixin
from apps.contracts.admin.mixins.display_mixin import ContractDisplayMixin
from apps.contracts.admin.mixins.save_mixin import ContractSaveMixin
from apps.core.enums import CaseStage, CaseStatus

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except Exception:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    show_change_link = True


class ContractAssignmentInline(BaseTabularInline):
    model = ContractAssignment
    extra = 1
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]


class SupplementaryAgreementPartyInline(BaseTabularInline):
    """补充协议当事人内联（嵌套在补充协议中）"""

    model = SupplementaryAgreementParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInline(BaseStackedInline):
    """补充协议内联（在合同中）"""

    model = SupplementaryAgreement
    extra = 0
    fields = ("name",)
    show_change_link = True


# 如果支持嵌套 Admin，添加当事人内联到补充协议
if BaseModelAdmin is not admin.ModelAdmin:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]  # type: ignore[attr-defined]


@admin.register(Contract)
class ContractAdmin(ContractDisplayMixin, ContractSaveMixin, ContractActionMixin, BaseModelAdmin):  # type: ignore[misc]
    class ContractAdminForm(forms.ModelForm[Contract]):
        representation_stages = forms.MultipleChoiceField(
            choices=CaseStage.choices,
            required=False,
            widget=forms.SelectMultiple,
            label=_("代理阶段"),
        )

        class Meta:
            model = Contract
            fields = "__all__"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            if not getattr(self.instance, "pk", None):
                self.fields["status"].initial = CaseStatus.ACTIVE
                self.fields["specified_date"].initial = timezone.localdate()
            self.fields["representation_stages"].initial = list(
                getattr(self.instance, "representation_stages", []) or []
            )

        def clean(self) -> dict[str, Any]:
            cleaned = super().clean() or {}
            try:
                from apps.contracts.validators import normalize_representation_stages

                ctype = cleaned.get("case_type")
                rep = cleaned.get("representation_stages") or []
                cleaned["representation_stages"] = normalize_representation_stages(ctype, rep, strict=False)
            except Exception:
                pass
            return cleaned

    form = ContractAdminForm
    list_display = (
        "id",
        "name",
        "case_type",
        "status",
        "start_date",
        "end_date",
        "get_primary_lawyer",
        "fee_mode",
        "fixed_amount",
        "risk_rate",
        "is_archived",
    )
    list_filter = ("case_type", "status", "fee_mode", "is_archived")
    search_fields = ("name",)
    readonly_fields = ("get_primary_lawyer_display", "filing_number")

    inlines: ClassVar = [
        ContractPartyInline,
        ContractAssignmentInline,
        SupplementaryAgreementInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"

