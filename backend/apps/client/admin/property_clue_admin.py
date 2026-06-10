from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html

from apps.client.models import PropertyClue, PropertyClueAttachment


def _get_property_clue_service() -> Any:
    """工厂函数：获取财产线索服务"""
    from apps.client.services.property_clue_service import PropertyClueService

    return PropertyClueService()


class PropertyClueAttachmentInlineForm(forms.ModelForm[PropertyClueAttachment]):  # pragma: no cover
    """财产线索附件内联表单"""

    file_upload = forms.FileField(required=False, label="上传文件")

    class Meta:  # pragma: no cover
        model = PropertyClueAttachment
        fields = ("file_name", "file_path")


class PropertyClueAttachmentInline(admin.TabularInline[PropertyClueAttachment, PropertyClueAttachment]):  # pragma: no cover
    """财产线索附件内联编辑"""

    model = PropertyClueAttachment
    form = PropertyClueAttachmentInlineForm
    extra = 1
    fields = ("file_upload", "file_name", "file_link", "uploaded_at")
    readonly_fields = ("file_link", "uploaded_at")

    def file_link(self, obj: PropertyClueAttachment) -> str:  # pragma: no cover
        """显示文件链接"""
        if obj.id:
            url = obj.media_url
            if url:
                return format_html('<a href="{}" target="_blank">{}</a>', url, obj.file_name)
        return obj.file_name if obj.file_name else ""

    file_link.short_description = "文件"  # type: ignore[attr-defined]


@admin.register(PropertyClue)
class PropertyClueAdmin(admin.ModelAdmin):  # pragma: no cover
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
    autocomplete_fields = ("client",)
    inlines: ClassVar = [PropertyClueAttachmentInline]

    fieldsets = (
        ("基本信息", {"fields": ("client", "clue_type", "content")}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request: HttpRequest) -> Any:  # pragma: no cover
        return super().get_queryset(request).select_related("client").prefetch_related("attachments")

    def clue_type_display(self, obj: PropertyClue) -> str:  # pragma: no cover
        """显示线索类型标签"""
        return obj.get_clue_type_display()

    clue_type_display.short_description = "线索类型"  # type: ignore[attr-defined]

    def content_preview(self, obj: PropertyClue) -> str:  # pragma: no cover
        """显示内容摘要"""
        if not obj.content:
            return ""
        return obj.content[:50] + ("..." if len(obj.content) > 50 else "")

    content_preview.short_description = "内容摘要"  # type: ignore[attr-defined]

    def attachment_count(self, obj: PropertyClue) -> str:  # pragma: no cover
        """显示附件数量"""
        # 使用预取缓存避免额外查询
        prefetched = (
            obj._prefetched_objects_cache.get("attachments") if hasattr(obj, "_prefetched_objects_cache") else None
        )
        count = len(prefetched) if prefetched is not None else obj.attachments.count()
        if count > 0:
            return format_html('<span style="color: green;">{}</span>', "%(count)d 个附件" % {"count": count})
        return "无附件"

    attachment_count.short_description = "附件"  # type: ignore[attr-defined]

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:  # pragma: no cover
        """处理附件内联表单的文件上传"""
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        service = _get_property_clue_service()
        for instance in instances:
            # 查找对应的 form
            for f in formset.forms:
                if f.instance == instance and f.cleaned_data.get("file_upload"):
                    uploaded_file = f.cleaned_data["file_upload"]
                    rel_path, _ = service.save_uploaded_file_to_dir(uploaded_file, rel_dir="property_clue_attachments")
                    instance.file_path = rel_path
                    instance.file_name = uploaded_file.name
                    break
            instance.save()

        formset.save_m2m()
