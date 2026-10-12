"""
文件夹槽位 Admin 配置

槽位是文书落位的语义锚点（受控词表）：键一经引用不可修改，名称可随时改。
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.documents.models import FolderSlot


@admin.register(FolderSlot)
class FolderSlotAdmin(admin.ModelAdmin):  # pragma: no cover
    """文件夹槽位管理"""

    list_display = ("key", "name", "description", "document_template_count", "is_active", "updated_at")
    search_fields = ("key", "name", "description")
    list_filter = ("is_active",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at", "document_template_count")

    fieldsets = (
        (None, {"fields": ("key", "name", "description")}),
        ("引用", {"fields": ("document_template_count",)}),
        ("状态", {"fields": ("is_active",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request: Any) -> Any:  # pragma: no cover
        return FolderSlot.objects.annotate(_doc_count=Count("document_templates"))

    @admin.display(description="占位文书数", ordering="_doc_count")
    def document_template_count(self, obj: Any) -> int:  # pragma: no cover
        return int(getattr(obj, "_doc_count", 0) or 0)

    def formfield_for_dbfield(self, db_field: Any, request: Any, **kwargs: Any) -> Any:  # pragma: no cover
        """槽位键在已有引用后禁止修改（身份标识）"""
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "key" and field is not None:
            obj_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            if obj_id:
                from apps.documents.models import DocumentTemplate

                field.required = True
                original = FolderSlot.objects.filter(pk=obj_id).first()
                if original and DocumentTemplate.objects.filter(folder_slot=original).exists():
                    field.widget.attrs["readonly"] = True
                    field.help_text = "已被文书模板引用，键不可修改（可改名称）"
        return field

    def save_model(self, request: Any, obj: FolderSlot, form: Any, change: bool) -> None:  # pragma: no cover
        if change:
            original = FolderSlot.objects.filter(pk=obj.pk).first()
            if original and original.key != obj.key:
                from apps.documents.models import DocumentTemplate

                if DocumentTemplate.objects.filter(folder_slot=original).exists():
                    from django.contrib import messages

                    messages.error(request, "槽位键已被引用，不可修改（可改名称）。")
                    return
        try:
            super().save_model(request, obj, form, change)
        except ValidationError:
            raise
