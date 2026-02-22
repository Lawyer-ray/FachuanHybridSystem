from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.client.models import PropertyClue, PropertyClueAttachment


class PropertyClueAttachmentInlineForm(forms.ModelForm[PropertyClueAttachment]):
    """财产线索附件内联表单"""

    file_upload = forms.FileField(required=False, label="上传文件")

    class Meta:
        model = PropertyClueAttachment
        fields = ("file_name", "file_path")

    def save(self, commit: bool = True) -> PropertyClueAttachment:
        instance = super().save(commit=False)

        if self.cleaned_data.get("file_upload"):
            uploaded_file = self.cleaned_data["file_upload"]
            from apps.client.services.storage import save_uploaded_file

            rel_path, _ = save_uploaded_file(uploaded_file, rel_dir="property_clue_attachments")
            instance.file_path = rel_path
            instance.file_name = uploaded_file.name

        if commit:
            instance.save()

        return instance


class PropertyClueAttachmentInline(admin.TabularInline[PropertyClueAttachment, PropertyClueAttachment]):
    """财产线索附件内联编辑"""

    model = PropertyClueAttachment
    form = PropertyClueAttachmentInlineForm
    extra = 1
    fields = ("file_upload", "file_name", "file_link", "uploaded_at")
    readonly_fields = ("file_link", "uploaded_at")

    def file_link(self, obj: PropertyClueAttachment) -> str:
        """显示文件链接"""
        if obj.id:
            url = obj.media_url()
            if url:
                return format_html('<a href="{}" target="_blank">{}</a>', url, obj.file_name)
        return obj.file_name if obj.file_name else ""

    file_link.short_description = _("文件")  # type: ignore[attr-defined]


@admin.register(PropertyClue)
class PropertyClueAdmin(admin.ModelAdmin[PropertyClue]):
    """财产线索管理"""

    list_display = (
        "id",
        "client",
        "clue_type_display",
        "content_preview",
        "attachment_count",
        "created_at",
        "updated_at",
    )
    list_filter = ("clue_type", "created_at")
    search_fields = ("client__name", "content")
    readonly_fields = ("created_at", "updated_at")
    inlines: ClassVar = [PropertyClueAttachmentInline]

    fieldsets = (
        (_("基本信息"), {"fields": ("client", "clue_type", "content")}),
        (_("时间信息"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def clue_type_display(self, obj: PropertyClue) -> str:
        """显示线索类型标签"""
        return obj.get_clue_type_display()

    clue_type_display.short_description = _("线索类型")  # type: ignore[attr-defined]

    def content_preview(self, obj: PropertyClue) -> str:
        """显示内容摘要"""
        if obj.content:
            preview = obj.content[:50]
            if len(obj.content) > 50:
                preview += "..."
            return preview
        return ""

    content_preview.short_description = _("内容摘要")  # type: ignore[attr-defined]

    def attachment_count(self, obj: PropertyClue) -> str:
        """显示附件数量"""
        count = obj.attachments.count()
        if count > 0:
            return format_html('<span style="color: green;">{} 个附件</span>', count)
        return "无附件"

    attachment_count.short_description = _("附件")  # type: ignore[attr-defined]
