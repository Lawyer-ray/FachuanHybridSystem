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

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import ModelForm

logger = logging.getLogger("apps.client")


def _get_admin_service() -> Any:
    """工厂函数：创建 ClientAdminService 实例"""
    from apps.client.services import ClientAdminService

    return ClientAdminService()


class ClientIdentityDocInlineForm(forms.ModelForm[ClientIdentityDoc]):
    upload = forms.FileField(required=False, label="上传文件")

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
        url = obj.media_url()
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
class ClientAdmin(admin.ModelAdmin[Client]):
    list_display: ClassVar = ("id", "name", "client_type", "is_our_client", "phone", "legal_representative")
    search_fields: ClassVar = ("name", "phone", "id_number")
    list_filter: ClassVar = ("client_type", "is_our_client")
    form = ClientAdminForm
    inlines: ClassVar = []

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
