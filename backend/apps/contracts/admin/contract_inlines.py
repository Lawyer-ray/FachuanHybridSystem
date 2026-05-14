from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.urls import reverse
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
        help_text=_("仅支持 PDF，最大 100MB"),
    )

    target_subdir = forms.CharField(
        required=False,
        label="保存子目录",
        help_text="先归属到当前合同文件夹，再保存到这里填写的子目录；留空时会按分类自动推荐。",
    )

    class Meta:
        model = FinalizedMaterial
        fields = ("file", "target_subdir", "category")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["category"].label = "文件用途分类"
        self.fields["category"].help_text = "用于自动推荐保存子目录，也用于后续归档识别。"
        if self.instance and self.instance.pk and self.instance.subdir_path:
            self.fields["target_subdir"].initial = self.instance.subdir_path

    def _has_existing_file(self) -> bool:
        return bool(
            str(getattr(self.instance, "file_path", "") or "").strip()
            or str(getattr(self.instance, "relative_file_path", "") or "").strip()
            or str(getattr(self.instance, "original_filename", "") or "").strip()
        )

    def _has_uploaded_file(self) -> bool:
        if not hasattr(self, "files") or self.files is None:
            return False
        try:
            return bool(self.files.get(self.add_prefix("file")))
        except Exception:
            return False

    def has_changed(self) -> bool:
        changed = super().has_changed()
        if not changed:
            return False

        # Ignore helper-only edits on rows that still have no actual file.
        # This prevents auto-filled subdir/category values from creating empty records.
        if self._has_existing_file() or self._has_uploaded_file():
            return True
        return False

    def save(self, commit: bool = True) -> FinalizedMaterial:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("file")
        target_subdir = str(self.cleaned_data.get("target_subdir") or "").strip()
        has_existing_file = self._has_existing_file()
        from apps.contracts.admin.wiring_admin import get_material_service

        svc = get_material_service()
        if uploaded_file:
            contract_id: int = instance.contract_id or self.instance.contract_id
            saved = svc.save_material_file(
                uploaded_file,
                contract_id,
                target_subdir=target_subdir,
                category=str(instance.category or ""),
            )
            instance.file_path = saved.legacy_file_path
            instance.storage_root_type = saved.root_type
            instance.subdir_path = saved.subdir_path
            instance.relative_file_path = saved.relative_file_path
            instance.original_filename = saved.original_filename
        elif (
            instance.pk
            and has_existing_file
            and target_subdir
            and target_subdir != str(instance.subdir_path or "").strip()
        ):
            contract_id = instance.contract_id or self.instance.contract_id
            moved = svc.move_material_file(
                instance,
                contract_id=contract_id,
                target_subdir=target_subdir,
                category=str(instance.category or ""),
            )
            instance.file_path = moved.legacy_file_path
            instance.storage_root_type = moved.root_type
            instance.subdir_path = moved.subdir_path
            instance.relative_file_path = moved.relative_file_path
            if not instance.original_filename:
                instance.original_filename = moved.original_filename
        if commit:
            instance.save()
        return instance


class FinalizedMaterialInline(BaseTabularInline):
    model = FinalizedMaterial
    form = FinalizedMaterialAdminForm
    extra = 0
    fields: ClassVar = ("file", "target_subdir", "category", "filename_link", "uploaded_at")
    readonly_fields: ClassVar = ("filename_link", "uploaded_at")
    classes = ("collapse",)

    @admin.display(description=_("原始文件名"))
    def filename_link(self, obj: FinalizedMaterial) -> str:
        from django.utils.html import format_html

        if obj.pk and obj.contract_id and obj.original_filename:
            url = reverse("admin:contracts_contract_preview_archive_material", args=[obj.contract_id, obj.pk])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.original_filename)
        return obj.original_filename or "-"

    def delete_model(self, request: HttpRequest, obj: FinalizedMaterial) -> None:
        from apps.contracts.admin.wiring_admin import get_material_service

        get_material_service().delete_material_file(obj)
        obj.delete()

    class Media:
        css = {"all": ("contracts/css/finalized_material_inline.css",)}


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra = 0
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]
    show_change_link = True

    class Media:
        js = ("contracts/js/party_role_auto.js",)


class ContractAssignmentInline(BaseTabularInline):
    model = ContractAssignment
    extra = 0
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]


class SupplementaryAgreementPartyInline(BaseTabularInline):
    """补充协议当事人内联（嵌套在补充协议中）"""

    model = SupplementaryAgreementParty
    extra = 0
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInline(BaseStackedInline):
    """补充协议内联（在合同中）"""

    model = SupplementaryAgreement
    extra = 0
    fields = ("name",)
    show_change_link = True
    classes = ("collapse",)


if BaseStackedInline is not admin.StackedInline:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]  # type: ignore[attr-defined]
