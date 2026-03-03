from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.client.models import Client, ClientIdentityDoc
from apps.core.admin.mixins import AdminImportExportMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import ModelForm

logger = logging.getLogger("apps.client")


def _get_admin_service() -> Any:
    """工厂函数：创建 ClientAdminService 实例"""
    from apps.client.services import ClientAdminService

    return ClientAdminService()


class ClientIdentityDocInlineForm(forms.ModelForm[ClientIdentityDoc]):
    upload = forms.FileField(required=False, label=_("上传文件"))

    class Meta:
        model = ClientIdentityDoc
        fields: ClassVar = ["doc_type", "upload"]


class ClientIdentityDocInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ClientIdentityDoc
    form = ClientIdentityDocInlineForm
    extra = 1
    fields: ClassVar = ("doc_type", "file_link", "upload")
    readonly_fields: ClassVar = ("file_link",)

    def file_link(self, obj: ClientIdentityDoc) -> str:
        url = obj.media_url
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, Path(obj.file_path or "").name)
        return ""

    file_link.short_description = _("文件")  # type: ignore[attr-defined]


class ClientAdminForm(forms.ModelForm[Client]):
    class Meta:
        model = Client
        fields = "__all__"

    class Media:
        css: ClassVar = {"all": ("client/admin.css",)}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        ct = None
        if self.instance and getattr(self.instance, "client_type", None):
            ct = self.instance.client_type
        elif "client_type" in self.data:
            ct = self.data.get("client_type")
        elif self.initial.get("client_type"):
            ct = self.initial.get("client_type")
        self.fields["id_number"].label = _("身份证号码") if ct == "natural" else _("统一社会信用代码")


@admin.register(Client)
class ClientAdmin(AdminImportExportMixin, admin.ModelAdmin[Client]):
    list_display: ClassVar = ("id", "name", "client_type", "is_our_client", "phone", "legal_representative")
    search_fields: ClassVar = ("name", "phone", "id_number")
    list_filter: ClassVar = ("client_type", "is_our_client")
    form = ClientAdminForm
    inlines: ClassVar = []
    export_model_name = "client"
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        return {"client_type": "legal"}

    def get_inlines(self, request: HttpRequest, obj: Client | None = None) -> list[type[Any]]:
        return [ClientIdentityDocInline]

    def save_formset(self, request: HttpRequest, form: ModelForm[Client], formset: Any, change: bool) -> None:
        # 收集需要处理的上传文件信息（在 save 之前）
        upload_info: list[dict[str, Any]] = []
        for f in formset.forms:
            if not f.cleaned_data:
                continue
            if f.cleaned_data.get("DELETE"):
                continue
            uploaded_file = f.cleaned_data.get("upload")
            if uploaded_file:
                upload_info.append(
                    {
                        "form": f,
                        "uploaded_file": uploaded_file,
                        "doc_type": f.cleaned_data.get("doc_type"),
                    }
                )

        # 调用父类 save，让 Django 处理保存和设置 new_objects 等属性
        formset.save()

        # 处理文件上传和重命名
        if upload_info:
            admin_service = _get_admin_service()
            client = form.instance

            for info in upload_info:
                instance = info["form"].instance
                if instance.pk:
                    admin_service.save_and_rename_file(
                        client_id=client.id,
                        client_name=client.name,
                        doc_id=instance.pk,
                        doc_type=info["doc_type"],
                        uploaded_file=info["uploaded_file"],
                    )

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.client.services.client_resolve_service import ClientResolveService

        svc = ClientResolveService()
        success = skipped = 0
        errors: list[str] = []
        for item in data_list:
            try:
                id_number = item.get("id_number")
                before = Client.objects.filter(id_number=id_number).exists() if id_number else False
                svc.resolve_with_attachments(item)
                if not before:
                    success += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append(str(exc))
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Client]) -> list[dict[str, Any]]:
        fields = ("name", "client_type", "id_number", "phone", "address",
                  "legal_representative", "legal_representative_id_number", "is_our_client")
        result = []
        for obj in queryset.prefetch_related("identity_docs", "property_clues__attachments"):
            d = {f: getattr(obj, f) for f in fields}
            d["identity_docs"] = [
                {"doc_type": doc.doc_type, "file_path": doc.file_path}
                for doc in obj.identity_docs.all()
                if doc.file_path
            ]
            d["property_clues"] = [
                {
                    "clue_type": clue.clue_type,
                    "content": clue.content,
                    "attachments": [
                        {"file_path": att.file_path, "file_name": att.file_name}
                        for att in clue.attachments.all()
                        if att.file_path
                    ],
                }
                for clue in obj.property_clues.all()
            ]
            result.append(d)
        return result

    def get_file_paths(self, queryset: QuerySet[Client]) -> list[str]:  # type: ignore[override]
        paths = []
        for obj in queryset.prefetch_related("identity_docs", "property_clues__attachments"):
            for doc in obj.identity_docs.all():
                if doc.file_path:
                    paths.append(doc.file_path)
            for clue in obj.property_clues.all():
                for att in clue.attachments.all():
                    if att.file_path:
                        paths.append(att.file_path)
        return paths
