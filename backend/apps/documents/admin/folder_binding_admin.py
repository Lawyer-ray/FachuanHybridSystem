"""
文书模板文件夹绑定 Admin 配置
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html

from apps.core.exceptions import NotFoundError
from apps.documents.models import DocumentTemplateFolderBinding, FolderTemplate


def _get_folder_template_admin_service() -> Any:
    from ..services import FolderTemplateAdminService

    return FolderTemplateAdminService()


class FolderNodeChoiceField(forms.ChoiceField):  # pragma: no cover
    """动态加载文件夹节点的选择字段"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        kwargs.setdefault("choices", [("", "---------")])
        super().__init__(*args, **kwargs)


class DocumentTemplateFolderBindingForm(forms.ModelForm[DocumentTemplateFolderBinding]):  # pragma: no cover
    """文书模板文件夹绑定表单"""

    folder_node_id = FolderNodeChoiceField(
        label="目标文件夹",
        help_text="选择文书生成后存放的文件夹位置",
    )

    class Meta:  # pragma: no cover
        model = DocumentTemplateFolderBinding
        fields: str = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
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

    def _get_folder_choices(self, folder_template: FolderTemplate) -> list[tuple[str, str]]:  # pragma: no cover
        """从文件夹模板结构中提取所有节点作为选项"""
        choices: list[tuple[str, str]] = [("", "---------")]
        structure = folder_template.structure
        if structure:
            self._extract_nodes(structure.get("children", []), choices, "")
        return choices

    def _extract_nodes(
        self, children: list[Any], choices: list[tuple[str, str]], prefix: str
    ) -> None:  # pragma: no cover
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
class DocumentTemplateFolderBindingAdmin(admin.ModelAdmin):  # pragma: no cover
    """
    文书模板文件夹绑定管理（旧·兼容）

    已被文书模板的「落位声明」（folder_slot 槽位解析）取代：
    - 不再允许新增；存量行只读核对，可删除
    - 列表展示每行「当前作用」：已被槽位取代 / 兜底生效（槽位未命中时回退旧路径）
    """

    form = DocumentTemplateFolderBindingForm
    change_form_template = "admin/documents/documenttemplatefolderbinding/change_form.html"
    change_list_template = "admin/documents/documenttemplatefolderbinding/change_list.html"

    list_display = (
        "document_template",
        "folder_template",
        "folder_path_display",
        "effect_display",
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

    list_select_related: ClassVar[tuple[str, ...]] = (
        "document_template",
        "document_template__folder_slot",
        "folder_template",
    )

    readonly_fields = (
        "document_template",
        "folder_template",
        "folder_node_id",
        "folder_node_path",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (None, {"fields": ("document_template", "folder_template", "folder_node_id")}),
        (
            "位置信息",
            {
                "fields": ("folder_node_path",),
                "classes": ("collapse",),
            },
        ),
        ("设置", {"fields": ("is_active",)}),
        (
            "时间信息",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    @admin.display(description="文件夹路径")
    def folder_path_display(self, obj: DocumentTemplateFolderBinding) -> Any:  # pragma: no cover
        """显示文件夹路径"""
        if obj.folder_node_path:
            return format_html('<span style="color: #666; font-family: monospace;">{}</span>', obj.folder_node_path)
        return "-"

    @admin.display(description="当前作用")
    def effect_display(self, obj: DocumentTemplateFolderBinding) -> Any:  # pragma: no cover
        """该绑定行在生成时刻是否仍起作用（槽位解析优先）"""
        from apps.documents.services.template.slot_resolution_service import RESOLVED_BY_SLOT, SlotResolutionService

        resolution = SlotResolutionService().resolve_binding_path(obj)
        if resolution.resolved_by == RESOLVED_BY_SLOT:
            return format_html('<span style="color: #999;">{}</span>', "已被槽位取代")
        if obj.document_template.folder_slot_id:
            return format_html('<span style="color: #b45309;">{}</span>', "兜底生效（骨架未提供该槽位）")
        return format_html('<span style="color: #1d4ed8;">{}</span>', "生效（模板未声明槽位）")
