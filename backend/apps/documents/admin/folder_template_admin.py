"""
文件夹模板 Admin 配置

Requirements: 6.1, 6.7
"""

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.core.enums import LegalStatus
from apps.core.exceptions import ValidationException
from apps.documents.models import (
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractType,
    FolderTemplate,
    FolderTemplateType,
)

logger = logging.getLogger(__name__)


def _get_admin_service() -> None:
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
        choices=FolderTemplate.LegalStatusMatchMode.choices,
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
            self.fields["legal_status_match_mode"].initial = self.instance.legal_status_match_mode or "any"

    def clean_structure(self) -> None:
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

    def save(self, commit=True) -> None:
        """保存时将多选字段值写入JSON字段,根据模板类型处理相应字段"""
        instance = super().save(commit=False)

        admin_service = _get_admin_service()
        save_data = admin_service.prepare_save_data(
            template_type=self.cleaned_data.get("template_type"),
            contract_types_field=self.cleaned_data.get("contract_types_field", []),
            case_types_field=self.cleaned_data.get("case_types_field", []),
            case_stage_field=self.cleaned_data.get("case_stage_field", ""),
            legal_statuses_field=self.cleaned_data.get("legal_statuses_field", []),
            legal_status_match_mode=self.cleaned_data.get("legal_status_match_mode", "any"),
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
class FolderTemplateAdmin(admin.ModelAdmin):
    """
    文件夹模板管理

    提供文件夹模板的 CRUD 操作和拖拽配置界面.
    """

    form = FolderTemplateForm  # 使用自定义表单

    list_display: tuple[Any, ...] = (
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

    list_filter: tuple[Any, ...] = (
        "template_type",
        "is_active",
    )

    search_fields: tuple[Any, ...] = ("name",)

    list_per_page: int = 50  # 每页显示50个模板

    ordering: ClassVar = ["-updated_at"]  # 按更新时间倒序排列

    readonly_fields: tuple[Any, ...] = (
        "created_at",
        "updated_at",
        "structure_preview",
    )

    fieldsets: tuple[Any, ...] = (
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

    actions: ClassVar = ["activate_templates", "deactivate_templates", "duplicate_templates"]

    # 自定义模板用于 SortableJS 拖拽界面
    change_form_template: str = "admin/documents/foldertemplate/change_form.html"

    class Media:
        css: ClassVar = {"all": ("documents/css/folder_tree.css", "documents/css/multi_select.css")}
        js: tuple[Any, ...] = ("documents/js/folder_tree.js", "documents/js/template_type_toggle.js")

    def template_type_display(self, obj) -> None:
        """显示模板类型"""
        return obj.template_type_display

    template_type_display.short_description = _("模板类型")

    def contract_types_display(self, obj) -> None:
        """显示合同类型"""
        return obj.contract_types_display

    contract_types_display.short_description = _("合同类型")

    def case_types_display(self, obj) -> None:
        """显示案件类型"""
        return obj.case_types_display

    case_types_display.short_description = _("案件类型")

    def case_stage_display(self, obj) -> None:
        """显示案件阶段"""
        stages = obj.case_stages or []
        if not stages:
            return "-"  # 空值显示为"-"
        return dict(DocumentCaseStage.choices).get(stages[0], stages[0])

    case_stage_display.short_description = _("案件阶段")

    def legal_statuses_display(self, obj) -> None:
        """显示诉讼地位"""
        if obj.template_type != "case":
            return "-"
        return obj.get_legal_statuses_display() or "任意"

    legal_statuses_display.short_description = _("我方诉讼地位")

    def legal_status_match_mode_display(self, obj) -> None:
        """显示诉讼地位匹配模式"""
        if obj.template_type != "case":
            return "-"
        return obj.get_legal_status_match_mode_display()

    legal_status_match_mode_display.short_description = _("匹配模式")

    def get_urls(self) -> None:
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

    def validate_structure_view(self, request) -> None:
        """AJAX结构验证视图"""
        admin_service = _get_admin_service()
        try:
            import json

            data = json.loads(request.body)
        except Exception:
            logger.exception("操作失败")

            data: dict[str, Any] = {}

        result = admin_service.validate_structure_ids(
            structure=data.get("structure"),
            template_id=data.get("template_id"),
        )
        return JsonResponse(result)

    def duplicate_report_view(self, request) -> None:
        """重复ID报告视图"""
        admin_service = _get_admin_service()
        report_data = admin_service.get_duplicate_report()
        return JsonResponse(report_data)

    def initialize_defaults_view(self, request) -> None:
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

        # 重定向回列表页面
        return redirect("admin:documents_foldertemplate_changelist")

    def get_structure_json_view(self, request, pk) -> None:
        """获取文件夹模板结构JSON(供AJAX调用)"""
        try:
            template = FolderTemplate.objects.get(pk=pk)
            return JsonResponse({"success": True, "structure": template.structure, "name": template.name})
        except FolderTemplate.DoesNotExist:
            return JsonResponse({"success": False, "error": "模板不存在"}, status=404)

    def get_form(self, request, obj=None, **kwargs) -> None:
        """获取表单实例,传入request对象"""
        FormClass = super().get_form(request, obj, **kwargs)

        class FormWithRequest(FormClass):
            def __init__(self, *args, **kwargs) -> None:
                kwargs["request"] = request
                super().__init__(*args, **kwargs)

        return FormWithRequest

    def save_model(self, request, obj, form, change) -> None:
        """保存模型 - 处理自动修复的结构并显示消息"""
        # 如果表单中的结构被自动修复了,需要更新对象
        if hasattr(form, "cleaned_data") and "structure" in form.cleaned_data:
            obj.structure = form.cleaned_data["structure"]

        # 显示自动修复消息
        if hasattr(form, "_fix_messages"):
            from django.contrib import messages

            for message in form._fix_messages:
                messages.success(request, f"✅ {message}")

        super().save_model(request, obj, form, change)

    def folder_count_display(self, obj) -> None:
        """显示文件夹数量"""
        count = self._count_folders(obj.structure)
        return count

    folder_count_display.short_description = _("文件夹数量")

    def _count_folders(self, structure) -> None:
        """递归计算文件夹数量"""
        if not structure:
            return 0
        count = 0
        children = structure.get("children", [])
        for child in children:
            count += 1
            count += self._count_folders(child)
        return count

    def structure_preview(self, obj) -> None:
        """文件夹结构预览"""
        if not obj.structure:
            return _("暂无结构")

        html = self._render_structure_tree(obj.structure)
        return mark_safe(f'<div class="folder-structure-preview">{html}</div>')

    structure_preview.short_description = _("结构预览")

    def _render_structure_tree(self, structure, level=0) -> None:
        """递归渲染文件夹树"""
        admin_service = _get_admin_service()
        return admin_service.render_structure_tree(structure, level)

    @admin.action(description=_("启用选中的模板"))
    def activate_templates(self, request, queryset) -> None:
        """批量启用模板"""
        updated = 0
        for template in queryset:
            if not template.is_active:
                template.is_active = True
                template.save(update_fields=["is_active"])
                updated += 1
        self.message_user(request, _(f"已启用 {updated} 个模板"))

    @admin.action(description=_("禁用选中的模板"))
    def deactivate_templates(self, request, queryset) -> None:
        """批量禁用模板"""
        updated = 0
        for template in queryset:
            if template.is_active:
                template.is_active = False
                template.save(update_fields=["is_active"])
                updated += 1
        self.message_user(request, _(f"已禁用 {updated} 个模板"))

    @admin.action(description=_("复制选中的模板"))
    def duplicate_templates(self, request, queryset) -> None:
        """批量复制文件夹模板"""
        admin_service = _get_admin_service()
        count = admin_service.batch_duplicate_templates(queryset)
        self.message_user(request, _(f"已复制 {count} 个模板"))
