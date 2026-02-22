from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.client.models import ClientIdentityDoc

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger("apps.client")


def _get_identity_doc_service() -> Any:
    """工厂函数：获取当事人证件服务"""
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    return ClientIdentityDocService()


class ClientIdentityDocForm(forms.ModelForm[ClientIdentityDoc]):
    """当事人证件表单"""

    file_upload = forms.FileField(
        label="上传文件",
        required=False,
        help_text="上传后将自动重命名为：当事人名称_证件类型.扩展名",
    )

    class Meta:
        model = ClientIdentityDoc
        fields: ClassVar = ["client", "doc_type", "file_path"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["file_upload"].help_text = f"当前文件：{Path(self.instance.file_path or '').name}"

    def save(self, commit: bool = True) -> ClientIdentityDoc:
        instance = super().save(commit=False)

        if self.cleaned_data.get("file_upload"):
            uploaded_file = self.cleaned_data["file_upload"]
            service = _get_identity_doc_service()
            instance.file_path = service.save_uploaded_file_to_dir(
                uploaded_file, rel_dir="client_identity_docs"
            )

        if commit:
            instance.save()
        return instance


@admin.register(ClientIdentityDoc)
class ClientIdentityDocAdmin(admin.ModelAdmin[ClientIdentityDoc]):
    form = ClientIdentityDocForm
    list_display = ("id", "client", "doc_type", "uploaded_at", "file_link")
    search_fields = ("client__name", "file_path")
    list_filter = ("doc_type",)
    actions = ["rename_files"]
    fields = ("client", "doc_type", "file_upload", "file_path")

    def file_link(self, obj: ClientIdentityDoc) -> str:
        url = obj.media_url()
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, Path(obj.file_path or "").name)
        return obj.file_path or ""

    file_link.short_description = _("文件")  # type: ignore[attr-defined]

    def save_model(self, request: HttpRequest, obj: ClientIdentityDoc, form: Any, change: bool) -> None:
        """保存时自动重命名文件"""
        super().save_model(request, obj, form, change)

        service = _get_identity_doc_service()
        try:
            service.rename_uploaded_file(obj)
            if change:
                messages.success(request, "文件已重命名为标准格式")
        except Exception as e:
            messages.warning(request, f"文件重命名失败: {e!s}")

    def rename_files(self, request: HttpRequest, queryset: QuerySet[ClientIdentityDoc, ClientIdentityDoc]) -> None:
        """批量重命名文件"""
        service = _get_identity_doc_service()
        success_count = 0
        error_count = 0

        for obj in queryset:
            try:
                service.rename_uploaded_file(obj)
                success_count += 1
            except Exception:
                logger.exception("批量重命名文件失败", extra={"doc_id": obj.pk})
                error_count += 1

        if success_count > 0:
            messages.success(request, f"成功重命名 {success_count} 个文件")
        if error_count > 0:
            messages.error(request, f"{error_count} 个文件重命名失败")

    rename_files.short_description = _("重命名选中的文件")  # type: ignore[attr-defined]
