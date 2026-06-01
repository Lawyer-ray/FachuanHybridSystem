from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import (
    ContractAssignment,
    ContractParty,
    FinalizedMaterial,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)

if TYPE_CHECKING:
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
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
        fields = ("file", "category")

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
    fields: ClassVar = ("file", "category", "filename_link", "uploaded_at")
    readonly_fields: ClassVar = ("filename_link", "uploaded_at")
    classes = ("collapse",)

    @admin.display(description=_("原始文件名"))
    def filename_link(self, obj: FinalizedMaterial) -> str:
        from django.utils.html import format_html

        if obj.file_path and obj.original_filename:
            url = f"/media/{obj.file_path}"
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.original_filename)
        return obj.original_filename or "-"

    def delete_model(self, request: HttpRequest, obj: FinalizedMaterial) -> None:
        from apps.contracts.admin.wiring_admin import get_material_service

        get_material_service().delete_material_file(obj.file_path)
        obj.delete()

    class Media:
        css = {"all": ("contracts/css/finalized_material_inline.css",)}


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]
    show_change_link = True

    class Media:
        js = ("contracts/js/party_role_auto.js",)


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
    classes = ("collapse",)


# 如果支持嵌套 Admin，添加当事人内联到补充协议
if BaseStackedInline is not admin.StackedInline:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]  # type: ignore[attr-defined]
