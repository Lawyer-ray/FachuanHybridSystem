from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    FinalizedMaterial,
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
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline


class FinalizedMaterialAdminForm(forms.ModelForm[FinalizedMaterial]):
    file = forms.FileField(
        required=False,
        label=_("上传文件"),
        help_text=_("仅支持 PDF，最大 20MB"),
    )

    class Meta:
        model = FinalizedMaterial
        fields = ("file", "category", "remark", "original_filename", "uploaded_at")

    def save(self, commit: bool = True) -> FinalizedMaterial:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file:
            from apps.contracts.admin.wiring_admin import get_material_service

            svc = get_material_service()
            contract_id: int = instance.contract_id or self.instance.contract_id
            rel_path, original_name = svc.save_material_file(uploaded_file, contract_id)
            instance.file_path = rel_path
            instance.original_filename = original_name
        if commit:
            instance.save()
        return instance


class FinalizedMaterialInline(BaseTabularInline):
    model = FinalizedMaterial
    form = FinalizedMaterialAdminForm
    extra = 1
    fields: ClassVar = ("file", "category", "remark", "original_filename", "uploaded_at")
    readonly_fields: ClassVar = ("original_filename", "uploaded_at")

    def delete_model(self, request: HttpRequest, obj: FinalizedMaterial) -> None:
        from apps.contracts.admin.wiring_admin import get_material_service

        get_material_service().delete_material_file(obj.file_path)
        obj.delete()


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
                logger.exception("操作失败")
            return cleaned

    form = ContractAdminForm
    list_display = (
        "id",
        "name_link",
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
        FinalizedMaterialInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).prefetch_related("assignments__lawyer")

