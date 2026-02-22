"""
文书模板文件夹绑定 Admin 配置
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import Field
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError
from apps.documents.models import DocumentTemplateFolderBinding, FolderTemplate


def _get_folder_template_admin_service() -> Any:
    from ..services import FolderTemplateAdminService

    return FolderTemplateAdminService()


class FolderNodeChoiceField(forms.ChoiceField):
    """动态加载文件夹节点的选择字段"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("choices", [("", "---------")])
        super().__init__(*args, **kwargs)


class DocumentTemplateFolderBindingForm(forms.ModelForm[DocumentTemplateFolderBinding]):
    """文书模板文件夹绑定表单"""

    folder_node_id = FolderNodeChoiceField(
        label=_("目标文件夹"),
        help_text=_("选择文书生成后存放的文件夹位置"),
    )

    class Meta:
        model = DocumentTemplateFolderBinding
        fields: str = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # 如果已选择文件夹模板,加载其节点选项
        folder_template_id: int | str | None = None
        if self.instance and self.instance.pk:
            folder_template_id = self.instance.folder_template_id
        elif self.data.get("folder_template"):
            folder_template_id = self.data.get("folder_template")

        if folder_template_id:
            try:
                service = _get_folder_template_admin_service()
                folder_template: FolderTemplate = service.get_folder_template_by_pk(folder_template_id)
                choices = self._get_folder_choices(folder_template)
                self.fields["folder_node_id"].choices = choices  # type: ignore[attr-defined]
            except NotFoundError:
                pass

    def _get_folder_choices(self, folder_template: FolderTemplate) -> list[tuple[str, str]]:
        """从文件夹模板结构中提取所有节点作为选项"""
        choices: list[tuple[str, str]] = [("", "---------")]
        structure = folder_template.structure
        if structure:
            self._extract_nodes(structure.get("children", []), choices, "")
        return choices

    def _extract_nodes(self, children: list[Any], choices: list[tuple[str, str]], prefix: str) -> None:
        """递归提取节点"""
        for child in children:
            node_id = child.get("id", "")
            node_name = child.get("name", "")
            display_name = f"{prefix}{node_name}" if prefix else node_name
            if node_id:
                choices.append((node_id, display_name))
            # 递归处理子节点
            sub_children = child.get("children", [])
            if sub_children:
                new_prefix = f"{display_name} / "
                self._extract_nodes(sub_children, choices, new_prefix)


@admin.register(DocumentTemplateFolderBinding)
class DocumentTemplateFolderBindingAdmin(admin.ModelAdmin[DocumentTemplateFolderBinding]):
    """文书模板文件夹绑定管理"""

    form = DocumentTemplateFolderBindingForm
    change_form_template = "admin/documents/documenttemplatefolderbinding/change_form.html"

    list_display = (
        "document_template",
        "folder_template",
        "folder_path_display",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "folder_template",
        "is_active",
        "document_template__template_type",
    )

    search_fields = (
        "document_template__name",
        "folder_template__name",
        "folder_node_path",
    )

    autocomplete_fields: ClassVar[list[str]] = ["document_template", "folder_template"]

    readonly_fields = ("folder_node_path", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("document_template", "folder_template", "folder_node_id")}),
        (
            _("位置信息"),
            {
                "fields": ("folder_node_path",),
                "classes": ("collapse",),
            },
        ),
        (_("设置"), {"fields": ("is_active",)}),
        (
            _("时间信息"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    class Media:
        js: ClassVar[tuple[str, ...]] = ("documents/js/folder_binding_admin.js",)

    def folder_path_display(self, obj: DocumentTemplateFolderBinding) -> Any:
        """显示文件夹路径"""
        if obj.folder_node_path:
            return format_html('<span style="color: #666; font-family: monospace;">{}</span>', obj.folder_node_path)
        return "-"

    folder_path_display.short_description = _("文件夹路径")  # type: ignore[attr-defined]

    def save_model(self, request: HttpRequest, obj: DocumentTemplateFolderBinding, form: Any, change: bool) -> None:
        """保存时自动计算路径"""
        # 路径会在模型的save方法中自动计算
        super().save_model(request, obj, form, change)
