"""
文件夹模板 Admin 配置

Requirements: 6.1, 6.7
"""

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.enums import LegalStatus
from apps.core.exceptions import NotFoundError
from apps.documents.models import (
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractType,
    FolderTemplate,
    FolderTemplateType,
    LegalStatusMatchMode,
)

logger = logging.getLogger(__name__)


def _get_admin_service() -> Any:
    """工厂函数:获取Admin服务实例"""
    from apps.documents.services.folder_template_admin_service import FolderTemplateAdminService

    return FolderTemplateAdminService()


class MultiSelectWidget(forms.CheckboxSelectMultiple):
    """多选复选框组件"""

    template_name: str = "django/forms/widgets/checkbox_select.html"
    option_template_name: str = "django/forms/widgets/checkbox_option.html"


class FolderTemplateForm(forms.ModelForm):
    """文件夹模板表单,包含ID验证逻辑和多选字段"""

    # 模板类型单选(必选)
    template_type = forms.ChoiceField(
        choices=FolderTemplateType.choices,
        widget=forms.RadioSelect,
        label=_("模板类型"),
        help_text=_("必须选择:合同文件夹模板或案件文件夹模板"),
    )

    # 合同类型多选(放在最上面)
    contract_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentContractType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("合同类型"),
        help_text=_("仅在选择'合同文件夹模板'时有效,可多选"),
    )

    # 案件类型多选
    case_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentCaseType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("案件类型"),
        help_text=_("仅在选择'案件文件夹模板'时有效,可多选"),
    )

    # 案件阶段单选
    case_stage_field = forms.ChoiceField(
        choices=[("", "不限")] + [(c.value, c.label) for c in DocumentCaseStage],
        widget=forms.Select,
        required=False,
        label=_("案件阶段"),
        help_text=_("仅在选择'案件文件夹模板'时有效,单选"),
    )

    # 诉讼地位多选
    legal_statuses_field = forms.MultipleChoiceField(
        choices=LegalStatus.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("我方诉讼地位"),
        help_text=_("仅在选择'案件文件夹模板'时有效,可多选;不选表示匹配任意诉讼地位"),
    )

    # 诉讼地位匹配模式
    legal_status_match_mode = forms.ChoiceField(
        choices=LegalStatusMatchMode.choices,
        widget=forms.Select,
        required=False,
        label=_("诉讼地位匹配模式"),
        help_text=_("仅在选择'案件文件夹模板'时有效"),
    )

    class Meta:
        model = FolderTemplate
        fields: ClassVar = ["name", "template_type", "is_active", "structure"]

    def __init__(self, *args, **kwargs) -> None:
        """初始化表单,保存request对象用于消息显示"""
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # 从实例加载已选值
        if self.instance and self.instance.pk:
            self.fields["template_type"].initial = self.instance.template_type
            self.fields["contract_types_field"].initial = self.instance.contract_types or []
            self.fields["case_types_field"].initial = self.instance.case_types or []
            # 案件阶段:从列表取第一个值或空
            case_stages = self.instance.case_stages or []
            self.fields["case_stage_field"].initial = case_stages[0] if case_stages else ""
            # 诉讼地位字段
            self.fields["legal_statuses_field"].initial = self.instance.legal_statuses or []
            self.fields["legal_status_match_mode"].initial = self.instance.legal_status_match_mode or LegalStatusMatchMode.ANY

    def clean_structure(self) -> Any:
        """验证并自动修复文件夹结构中的重复ID"""
        structure = self.cleaned_data.get("structure")

        if not structure:
            return structure

        admin_service = _get_admin_service()

        # 准备验证数据
        form_data = {"structure": structure, "id": self.instance.id if self.instance.pk else None}

        # 验证并尝试自动修复
        validation_result = admin_service.validate_and_fix_template_form(form_data)

        if not validation_result["is_valid"]:
            # 如果验证失败且无法修复,显示错误
            error_messages = validation_result["errors"]
            if len(error_messages) == 1:
                raise forms.ValidationError(error_messages[0])
            else:
                combined_message = "文件夹结构验证失败:" + ";".join(error_messages)
                raise forms.ValidationError(combined_message)

        # 如果自动修复了重复ID,使用修复后的结构
        if validation_result["is_fixed"]:
            fixed_structure = validation_result["fixed_structure"]
            fix_messages = validation_result["fix_messages"]

            # 保存修复消息,在save_model中显示
            self._fix_messages = fix_messages

            return fixed_structure

        return structure

    def save(self, commit: bool = True) -> Any:
        """保存时将多选字段值写入JSON字段,根据模板类型处理相应字段"""
        instance = super().save(commit=False)

        admin_service = _get_admin_service()
        save_data = admin_service.prepare_save_data(
            template_type=self.cleaned_data.get("template_type"),
            contract_types_field=self.cleaned_data.get("contract_types_field", []),
            case_types_field=self.cleaned_data.get("case_types_field", []),
            case_stage_field=self.cleaned_data.get("case_stage_field", ""),
            legal_statuses_field=self.cleaned_data.get("legal_statuses_field", []),
            legal_status_match_mode=self.cleaned_data.get("legal_status_match_mode", LegalStatusMatchMode.ANY),
        )

        instance.template_type = save_data["template_type"]
        instance.contract_types = save_data["contract_types"]
        instance.case_types = save_data["case_types"]
        instance.case_stages = save_data["case_stages"]
        instance.legal_statuses = save_data["legal_statuses"]
        instance.legal_status_match_mode = save_data["legal_status_match_mode"]

        if commit:
            instance.save()
        return instance


@admin.register(FolderTemplate)
class FolderTemplateAdmin(admin.ModelAdmin[FolderTemplate]):  # type: ignore[type-arg]
    """
    文件夹模板管理

    提供文件夹模板的 CRUD 操作和拖拽配置界面.
    """

    form = FolderTemplateForm  # 使用自定义表单

    list_display: ClassVar[tuple[str, ...]] = (
        "name",
        "template_type_display",
        "contract_types_display",
        "case_types_display",
        "case_stage_display",
        "legal_statuses_display",
        "legal_status_match_mode_display",
        "is_active",
        "folder_count_display",
        "updated_at",
    )

    list_filter: ClassVar[tuple[str, ...]] = (
        "template_type",
        "is_active",
    )

    search_fields: ClassVar[tuple[str, ...]] = ("name",)

    list_per_page: int = 50

    ordering: ClassVar[list[str]] = ["-updated_at"]

    readonly_fields: ClassVar[tuple[str, ...]] = (
        "created_at",
        "updated_at",
        "structure_preview",
    )

    fieldsets: ClassVar[tuple[Any, ...]] = (
        (None, {"fields": ("name",)}),
        (_("模板类型"), {"fields": ("template_type",), "description": _("选择此模板用于合同还是案件,必须二选一")}),
        (
            _("适用范围"),
            {
                "fields": (
                    "contract_types_field",
                    "case_types_field",
                    "case_stage_field",
                    "legal_statuses_field",
                    "legal_status_match_mode",
                ),
                "description": _("根据模板类型选择相应的适用范围:合同模板选择合同类型,案件模板选择案件类型和阶段"),
            },
        ),
        (_("状态"), {"fields": ("is_active",)}),
        (
            _("文件夹结构"),
            {"fields": ("structure", "structure_preview"), "description": _("使用 JSON 格式定义文件夹层级结构")},
        ),
        (_("时间信息"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions: ClassVar[list[str]] = ["activate_templates", "deactivate_templates", "duplicate_templates"]

    change_form_template: str = "admin/documents/foldertemplate/change_form.html"

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {
            LegalStatusMatchMode.ALL: ("documents/css/folder_tree.css", "documents/css/multi_select.css")
        }
        js: ClassVar[tuple[str, ...]] = (
            "documents/js/folder_tree.js",
            "documents/js/template_type_toggle.js",
        )

    @admin.display(description=_("模板类型"))
    def template_type_display(self, obj: FolderTemplate) -> str:
        """显示模板类型"""
        return obj.template_type_display  # type: ignore[no-any-return]

    @admin.display(description=_("合同类型"))
    def contract_types_display(self, obj: FolderTemplate) -> str:
        """显示合同类型"""
        return obj.contract_types_display  # type: ignore[no-any-return]

    @admin.display(description=_("案件类型"))
    def case_types_display(self, obj: FolderTemplate) -> str:
        """显示案件类型"""
        return obj.case_types_display  # type: ignore[no-any-return]

    @admin.display(description=_("案件阶段"))
    def case_stage_display(self, obj: FolderTemplate) -> str:
        """显示案件阶段"""
        stages = obj.case_stages or []
        if not stages:
            return "-"
        return dict(DocumentCaseStage.choices).get(stages[0], stages[0])  # type: ignore[return-value]

    @admin.display(description=_("我方诉讼地位"))
    def legal_statuses_display(self, obj: FolderTemplate) -> str:
        """显示诉讼地位"""
        if obj.template_type != "case":
            return "-"
        return obj.get_legal_statuses_display() or "任意"  # type: ignore[no-any-return]

    @admin.display(description=_("匹配模式"))
    def legal_status_match_mode_display(self, obj: FolderTemplate) -> str:
        """显示诉讼地位匹配模式"""
        if obj.template_type != "case":
            return "-"
        return obj.get_legal_status_match_mode_display()  # type: ignore[no-any-return]

    def get_urls(self) -> list[Any]:
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "validate-structure/",
                self.admin_site.admin_view(self.validate_structure_view),
                name="documents_foldertemplate_validate_structure",
            ),
            path(
                "duplicate-report/",
                self.admin_site.admin_view(self.duplicate_report_view),
                name="documents_foldertemplate_duplicate_report",
            ),
            path(
                "initialize-defaults/",
                self.admin_site.admin_view(self.initialize_defaults_view),
                name="documents_foldertemplate_initialize_defaults",
            ),
            path(
                "<int:pk>/structure-json/",
                self.admin_site.admin_view(self.get_structure_json_view),
                name="documents_foldertemplate_structure_json",
            ),
        ]
        return custom_urls + urls

    def validate_structure_view(self, request: Any) -> JsonResponse:
        """AJAX结构验证视图"""
        admin_service = _get_admin_service()
        try:
            import json

            data: dict[str, Any] = json.loads(request.body)
        except Exception:
            logger.exception("操作失败")
            data = {}

        result = admin_service.validate_structure_ids(
            structure=data.get("structure"),
            template_id=data.get("template_id"),
        )
        return JsonResponse(result)

    def duplicate_report_view(self, request: Any) -> JsonResponse:
        """重复ID报告视图"""
        admin_service = _get_admin_service()
        report_data = admin_service.get_duplicate_report()
        return JsonResponse(report_data)

    def initialize_defaults_view(self, request: Any) -> Any:
        """初始化默认模板视图"""
        from django.contrib import messages
        from django.shortcuts import redirect

        admin_service = _get_admin_service()
        result = admin_service.initialize_default_templates()

        for item in result.get("messages", []):
            level = item.get("level")
            message = item.get("message")
            if not message:
                continue
            if level == "success":
                messages.success(request, message)
            elif level == "info":
                messages.info(request, message)
            elif level == "warning":
                messages.warning(request, message)
            else:
                messages.error(request, message)

        return redirect("admin:documents_foldertemplate_changelist")

    def get_structure_json_view(self, request: Any, pk: int) -> JsonResponse:
        """获取文件夹模板结构JSON(供AJAX调用)"""
        admin_service = _get_admin_service()
        try:
            result: dict[str, Any] = admin_service.get_structure_json(pk)
            return JsonResponse(result)
        except NotFoundError:
            return JsonResponse({"success": False, "error": "模板不存在"}, status=404)

    def get_form(self, request: Any, obj: FolderTemplate | None = None, **kwargs: Any) -> Any:
        """获取表单实例,传入request对象"""
        FormClass = super().get_form(request, obj, **kwargs)

        class FormWithRequest(FormClass):  # type: ignore[valid-type]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                kwargs["request"] = request
                super().__init__(*args, **kwargs)

        return FormWithRequest

    def save_model(self, request: Any, obj: FolderTemplate, form: Any, change: bool) -> None:
        """保存模型 - 处理自动修复的结构并显示消息"""
        if hasattr(form, "cleaned_data") and "structure" in form.cleaned_data:
            obj.structure = form.cleaned_data["structure"]

        if hasattr(form, "_fix_messages"):
            from django.contrib import messages

            for message in form._fix_messages:
                messages.success(request, "✅ " + str(message))

        super().save_model(request, obj, form, change)

    @admin.display(description=_("文件夹数量"))
    def folder_count_display(self, obj: FolderTemplate) -> int:
        """显示文件夹数量"""
        return self._count_folders(obj.structure)

    def _count_folders(self, structure: Any) -> int:
        """递归计算文件夹数量"""
        if not structure:
            return 0
        count = 0
        children = structure.get("children", [])
        for child in children:
            count += 1
            count += self._count_folders(child)
        return count

    @admin.display(description=_("结构预览"))
    def structure_preview(self, obj: FolderTemplate) -> Any:
        """文件夹结构预览"""
        if not obj.structure:
            return _("暂无结构")

        html = self._render_structure_tree(obj.structure)
        return format_html('<div class="folder-structure-preview">{}</div>', html)

    def _render_structure_tree(self, structure: Any, level: int = 0) -> Any:
        """递归渲染文件夹树"""
        admin_service = _get_admin_service()
        return admin_service.render_structure_tree(structure, level)

    @admin.action(description=_("启用选中的模板"))
    def activate_templates(self, request: Any, queryset: Any) -> None:
        """批量启用模板"""
        admin_service = _get_admin_service()
        updated: int = admin_service.batch_activate(queryset)
        self.message_user(request, _("已启用 %(count)d 个模板") % {"count": updated})

    @admin.action(description=_("禁用选中的模板"))
    def deactivate_templates(self, request: Any, queryset: Any) -> None:
        """批量禁用模板"""
        admin_service = _get_admin_service()
        updated: int = admin_service.batch_deactivate(queryset)
        self.message_user(request, _("已禁用 %(count)d 个模板") % {"count": updated})

    @admin.action(description=_("复制选中的模板"))
    def duplicate_templates(self, request: Any, queryset: Any) -> None:
        """批量复制文件夹模板"""
        admin_service = _get_admin_service()
        count = admin_service.batch_duplicate_templates(queryset)
        self.message_user(request, _("已复制 %(count)d 个模板") % {"count": count})
