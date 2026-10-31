"""
文件夹模板 Admin 配置

Requirements: 6.1, 6.7
"""

import json
import logging
from functools import lru_cache
from typing import Any

from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from apps.core.exceptions import NotFoundError
from apps.core.models.enums import LegalStatus
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
    from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService

    return FolderTemplateAdminService()


@lru_cache(maxsize=1)
def _slot_vocabulary() -> tuple[dict[str, str], dict[str, str]]:
    """返回（槽位 key→标签、key→分类）词表。

    changelist 的 ``slots_provided_display`` 每行都会调用，而词表是**全表常量**：
    原实现每行跑两次全表查询（get_slot_label_map 的 all() +
    values_list("key","category")），N 行就变成 2N 次查询。词表进程内缓存，
    一次查询同时拿到两列。
    注意：必定为新写槽位时需重启进程（admin 场景可接受）。
    """
    from apps.documents.models import FolderSlot

    slots = list(FolderSlot.objects.all())
    # 标签口径必须与 FolderSlot.__str__ 一致（名称 (key) · 短分类），否则预览树与列表徽标会不一致
    labels = {slot.key: str(slot) for slot in slots}
    key_to_cat = {slot.key: slot.category for slot in slots}
    return labels, key_to_cat


class MultiSelectWidget(forms.CheckboxSelectMultiple):  # pragma: no cover
    """多选复选框组件"""

    template_name: str = "django/forms/widgets/checkbox_select.html"
    option_template_name: str = "django/forms/widgets/checkbox_option.html"


class FolderTemplateForm(forms.ModelForm):  # pragma: no cover
    """文件夹模板表单,包含ID验证逻辑和多选字段"""

    # 模板类型单选(必选)
    template_type = forms.ChoiceField(
        choices=FolderTemplateType.choices,
        widget=forms.RadioSelect,
        label="模板类型",
        help_text="必须选择:合同文件夹模板或案件文件夹模板",
    )

    # 合同类型多选(放在最上面)
    contract_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentContractType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="合同类型",
        help_text="仅在选择'合同文件夹模板'时有效,可多选",
    )

    # 案件类型多选
    case_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentCaseType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="案件类型",
        help_text="仅在选择'案件文件夹模板'时有效,可多选",
    )

    # 案件阶段单选
    case_stage_field = forms.ChoiceField(
        choices=[("", "不限")] + [(c.value, c.label) for c in DocumentCaseStage],
        widget=forms.Select,
        required=False,
        label="案件阶段",
        help_text="仅在选择'案件文件夹模板'时有效,单选",
    )

    # 诉讼地位多选
    legal_statuses_field = forms.MultipleChoiceField(
        choices=LegalStatus.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="我方诉讼地位",
        help_text="仅在选择'案件文件夹模板'时有效,可多选;不选表示匹配任意诉讼地位",
    )

    # 诉讼地位匹配模式
    legal_status_match_mode = forms.ChoiceField(
        choices=LegalStatusMatchMode.choices,
        widget=forms.Select,
        required=False,
        label="诉讼地位匹配模式",
        help_text="仅在选择'案件文件夹模板'时有效",
    )

    class Meta:  # pragma: no cover
        model = FolderTemplate
        fields = ["name", "template_type", "is_active", "structure"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
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
            self.fields["legal_status_match_mode"].initial = (
                self.instance.legal_status_match_mode or LegalStatusMatchMode.ANY
            )

    def clean_structure(self) -> Any:  # pragma: no cover
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

        # 槽位 kind 合法性：只允许词表内的键（防手写 JSON 打错字静默失效）
        from apps.documents.services.template.folder_template.admin_service import validate_slot_kinds

        bad_kinds = validate_slot_kinds(structure)
        if bad_kinds:
            raise forms.ValidationError(
                "以下节点的槽位标记不在词表中（请到「文件夹槽位」核对或清除）：" + "；".join(bad_kinds)
            )

        return structure

    def save(self, commit: bool = True) -> Any:  # pragma: no cover
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
class FolderTemplateAdmin(admin.ModelAdmin):  # pragma: no cover
    """
    文件夹模板管理

    提供文件夹模板的 CRUD 操作和拖拽配置界面.
    """

    form = FolderTemplateForm  # 使用自定义表单

    list_display = (
        "id",
        "name",
        "template_type_display",
        "contract_types_display",
        "case_types_display",
        "case_stage_display",
        "legal_statuses_display",
        "legal_status_match_mode_display",
        "is_active",
        "folder_count_display",
        "slots_provided_display",
        "updated_at",
    )

    list_filter = (
        "template_type",
        "is_active",
    )

    search_fields = ("name",)

    list_per_page = 50

    ordering = ("-updated_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "structure_preview",
    )

    fieldsets = (
        (None, {"fields": ("name",)}),
        ("模板类型", {"fields": ("template_type",)}),
        (
            "适用范围",
            {
                "fields": (
                    "contract_types_field",
                    "case_types_field",
                    "case_stage_field",
                    "legal_statuses_field",
                    "legal_status_match_mode",
                ),
            },
        ),
        ("状态", {"fields": ("is_active",)}),
        (
            "文件夹结构",
            {"fields": ("structure", "structure_preview")},
        ),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["activate_templates", "deactivate_templates", "duplicate_templates"]

    change_form_template = "admin/documents/foldertemplate/change_form.html"
    change_list_template = "admin/documents/foldertemplate/change_list.html"

    class Media:  # pragma: no cover
        css = {LegalStatusMatchMode.ALL: ("documents/css/folder_tree.css", "documents/css/multi_select.css")}
        js = (
            "documents/js/folder_editor.js",
            "documents/js/id_validation_manager.js",
            "documents/js/template_type_toggle.js",
        )

    @admin.display(description="模板类型")
    def template_type_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示模板类型"""
        return str(obj.template_type_display)

    @admin.display(description="合同类型")
    def contract_types_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示合同类型"""
        return str(obj.contract_types_display)

    @admin.display(description="案件类型")
    def case_types_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示案件类型"""
        return str(obj.case_types_display)

    @admin.display(description="案件阶段")
    def case_stage_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示案件阶段"""
        stages = obj.case_stages or []
        if not stages:
            return "-"
        stage_label = dict(DocumentCaseStage.choices).get(stages[0], stages[0])
        return str(stage_label)

    @admin.display(description="我方诉讼地位")
    def legal_statuses_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示诉讼地位"""
        if obj.template_type != "case":
            return "-"
        return str(obj.get_legal_statuses_display() or "任意")

    @admin.display(description="匹配模式")
    def legal_status_match_mode_display(self, obj: FolderTemplate) -> str:  # pragma: no cover
        """显示诉讼地位匹配模式"""
        if obj.template_type != "case":
            return "-"
        return str(obj.get_legal_status_match_mode_display())

    def render_change_form(
        self, request: Any, context: Any, add: bool = False, change: bool = False, form_url: str = "", obj: Any = None
    ) -> Any:  # pragma: no cover
        """注入槽位词表（结构编辑器节点的 kind 下拉数据源；json_script 负责序列化）"""
        from apps.documents.models import FolderSlot

        context["fc_slots_json"] = [
            {"key": s.key, "label": str(s)}
            for s in FolderSlot.objects.filter(is_active=True).order_by("category", "name")
        ]
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def get_urls(self) -> list[Any]:  # pragma: no cover
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

    def validate_structure_view(self, request: Any) -> JsonResponse:  # pragma: no cover
        """AJAX结构验证视图"""
        admin_service = _get_admin_service()
        try:
            import json

            data: dict[str, Any] = json.loads(request.body)
        except json.JSONDecodeError:
            logger.exception("操作失败")
            data = {}

        result = admin_service.validate_structure_ids(
            structure=data.get("structure"),
            template_id=data.get("template_id"),
        )
        return JsonResponse(result)

    def duplicate_report_view(self, request: Any) -> JsonResponse:  # pragma: no cover
        """重复ID报告视图"""
        admin_service = _get_admin_service()
        report_data = admin_service.get_duplicate_report()
        return JsonResponse(report_data)

    def initialize_defaults_view(self, request: Any) -> Any:  # pragma: no cover
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

    def get_structure_json_view(self, request: Any, pk: int) -> JsonResponse:  # pragma: no cover
        """获取文件夹模板结构JSON(供AJAX调用)"""
        admin_service = _get_admin_service()
        try:
            result: dict[str, Any] = admin_service.get_structure_json(pk)
            return JsonResponse(result)
        except NotFoundError:
            return JsonResponse({"success": False, "error": "模板不存在"}, status=404)

    def save_model(self, request: Any, obj: FolderTemplate, form: Any, change: bool) -> None:  # pragma: no cover
        """保存模型 - 处理自动修复的结构并显示消息"""
        if hasattr(form, "cleaned_data") and "structure" in form.cleaned_data:
            obj.structure = form.cleaned_data["structure"]

        if hasattr(form, "_fix_messages"):
            from django.contrib import messages

            for message in form._fix_messages:
                messages.success(request, "✅ " + str(message))

        super().save_model(request, obj, form, change)

    @admin.display(description="文件夹数量")
    def folder_count_display(self, obj: FolderTemplate) -> int:  # pragma: no cover
        """显示文件夹数量"""
        return self._count_folders(obj.structure)

    @admin.display(description="提供槽位")
    def slots_provided_display(self, obj: FolderTemplate) -> Any:  # pragma: no cover
        """骨架 structure 中标记的槽位（kind）：「N 类 + 分类聚合计数」，悬停（title）看全量"""
        from collections import Counter

        from django.utils.html import format_html

        from apps.documents.models.choices import FolderSlotCategory

        kinds: list[str] = []
        seen: set[str] = set()

        def walk(children: Any) -> None:
            for child in children or []:
                if not isinstance(child, dict):
                    continue
                kind = child.get("kind")
                if kind and kind not in seen:
                    seen.add(kind)
                    kinds.append(kind)
                walk(child.get("children"))

        walk((obj.structure or {}).get("children"))
        if not kinds:
            return format_html('<span style="color: #999;">—</span>')

        labels, key_to_cat = _slot_vocabulary()
        cat_counter = Counter(key_to_cat.get(kind, "") for kind in kinds)

        summary = "　".join(
            f"{FolderSlotCategory(cat).label}×{n}" for cat in FolderSlotCategory if (n := cat_counter.get(cat, 0))
        )
        full_text = "、".join(labels.get(kind, kind) for kind in kinds)

        return format_html(
            '<b>{} 类</b><br><span style="color: #666; font-size: 11px;" title="{}">{}</span>',
            len(kinds),
            full_text,
            summary,
        )

    def _count_folders(self, structure: Any) -> int:  # pragma: no cover
        """递归计算文件夹数量"""
        if not structure:
            return 0
        count = 0
        children = structure.get("children", [])
        for child in children:
            count += 1
            count += self._count_folders(child)
        return count

    @admin.display(description="结构预览")
    def structure_preview(self, obj: FolderTemplate) -> Any:  # pragma: no cover
        """文件夹结构预览"""
        if not obj.structure:
            return "暂无结构"

        admin_service = _get_admin_service()
        return admin_service.render_structure_preview(obj.structure)

    def _render_structure_tree(self, structure: Any, level: int = 0) -> Any:  # pragma: no cover
        """递归渲染文件夹树"""
        admin_service = _get_admin_service()
        return admin_service.render_structure_tree(structure, level)

    @admin.action(description="启用选中的模板")
    def activate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量启用模板"""
        admin_service = _get_admin_service()
        updated: int = admin_service.batch_activate(queryset)
        self.message_user(request, "已启用 %(count)d 个模板" % {"count": updated})

    @admin.action(description="禁用选中的模板")
    def deactivate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量禁用模板"""
        admin_service = _get_admin_service()
        updated: int = admin_service.batch_deactivate(queryset)
        self.message_user(request, "已禁用 %(count)d 个模板" % {"count": updated})

    @admin.action(description="复制选中的模板")
    def duplicate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量复制文件夹模板"""
        admin_service = _get_admin_service()
        count = admin_service.batch_duplicate_templates(queryset)
        self.message_user(request, "已复制 %(count)d 个模板" % {"count": count})
