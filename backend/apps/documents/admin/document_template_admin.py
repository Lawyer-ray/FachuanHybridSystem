"""
文书模板 Admin 配置

Requirements: 6.1, 2.9, 2.10
"""

import json
import logging
from typing import Any, cast

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from apps.core.models.enums import LegalStatus
from apps.documents.models import (
    DocumentArchiveSubType,
    DocumentCaseFileSubType,
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractSubType,
    DocumentContractType,
    DocumentTemplate,
    DocumentTemplateFolderBinding,
    DocumentTemplateType,
    LegalStatusMatchMode,
)
from apps.documents.storage import list_docx_templates_files

from .template_admin_display_mixin import TemplateAdminDisplayMixin
from .template_admin_views_mixin import TemplateAdminViewsMixin

logger = logging.getLogger(__name__)


def _get_admin_service() -> Any:
    """工厂函数获取Admin服务"""
    from apps.documents.services.template.document_template.admin_service import DocumentTemplateAdminService

    return DocumentTemplateAdminService()


class DocumentTemplateFolderBindingInline(admin.TabularInline):  # pragma: no cover
    """文书模板文件夹绑定内联"""

    model = DocumentTemplateFolderBinding
    extra = 1
    fields = ("folder_template", "folder_node_id", "folder_node_path", "is_active")
    readonly_fields = ("folder_node_path",)
    autocomplete_fields = ["folder_template"]

    class Media:  # pragma: no cover
        css = {LegalStatusMatchMode.ALL: ("documents/css/folder_binding_inline.css",)}
        js = ("admin/js/jquery.init.js", "documents/js/folder_binding_inline.js")


class DocumentTemplateForm(forms.ModelForm):  # pragma: no cover
    """文书模板表单,包含模板类型和适用范围选择(与文件夹模板保持一致)"""

    # 模板类型单选(必选)
    template_type = forms.ChoiceField(
        choices=DocumentTemplateType.choices,
        widget=forms.RadioSelect,
        label="模板类型",
        help_text="选择此模板用于合同、案件还是归档",
    )

    # 合同子类型单选(仅合同模板时显示)
    contract_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentContractSubType],
        widget=forms.RadioSelect,
        required=False,
        label="合同子类型",
        help_text="仅在选择'合同文书模板'时有效,必须选择合同模板或补充协议模板",
    )

    case_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentCaseFileSubType],
        widget=forms.RadioSelect,
        required=False,
        label="案件文件子类型",
        help_text="仅在选择'案件文书模板'时有效,可选择诉状材料、证据材料、授权委托材料等",
    )

    archive_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentArchiveSubType],
        widget=forms.RadioSelect,
        required=False,
        label="归档文件子类型",
        help_text="仅在选择'归档文件模板'时有效,可选择案卷封面、结案归档登记表等",
    )

    # 合同类型多选(仅合同模板时显示)
    contract_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentContractType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="合同类型",
        help_text="仅在选择'合同文书模板'时有效,可多选",
    )

    # 案件类型多选(仅案件模板时显示)
    case_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentCaseType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="案件类型",
        help_text="仅在选择'案件文书模板'时有效,可多选",
    )

    # 案件阶段单选(仅案件模板时显示)
    case_stage_field = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentCaseStage],
        widget=forms.Select,
        required=False,
        label="案件阶段",
        help_text="仅在选择'案件文书模板'时有效,单选",
    )

    # 我方诉讼地位多选(仅案件模板时显示)
    legal_statuses_field = forms.MultipleChoiceField(
        choices=LegalStatus.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="我方诉讼地位",
        help_text="可单选或多选;不选表示匹配任意诉讼地位",
    )

    # 诉讼地位匹配模式单选(仅案件模板时显示)
    legal_status_match_mode = forms.ChoiceField(
        choices=LegalStatusMatchMode.choices,
        widget=forms.RadioSelect,
        required=False,
        initial=LegalStatusMatchMode.ANY,
        label="诉讼地位匹配模式",
    )

    # 适用机构(案件模板时显示)
    applicable_institutions_field = forms.CharField(
        required=False,
        label="适用机构",
        help_text="输入机构名称后回车添加,支持搜索法院名称",
        widget=forms.Textarea(
            attrs={
                "id": "id_applicable_institutions_field",
                "style": "display:none;",
                "rows": "1",
            }
        ),
    )

    # 从已有文件中选择(新增)
    existing_file = forms.ChoiceField(
        choices=[],
        required=False,
        label="从模板库选择",
        help_text="从 docx_templates 目录中选择已有的模板文件(不会复制文件)",
    )

    class Meta:  # pragma: no cover
        model = DocumentTemplate
        fields = [
            "name",
            "template_type",
            "contract_sub_type",
            "case_sub_type",
            "archive_sub_type",
            "file",
            "file_path",
            "is_active",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        super().__init__(*args, **kwargs)

        # 动态加载已有文件列表
        existing_files = list_docx_templates_files()
        existing_file_field = cast(forms.ChoiceField, self.fields["existing_file"])
        existing_file_field.choices = [("", "-- 不选择 / 上传新文件 --")] + existing_files

        # 从实例加载已选值
        if self.instance and self.instance.pk:
            admin_service = _get_admin_service()
            initial_values = admin_service.get_form_initial_values(self.instance, existing_files)

            self.fields["template_type"].initial = initial_values["template_type"]
            self.fields["contract_sub_type"].initial = initial_values["contract_sub_type"]
            self.fields["case_sub_type"].initial = initial_values["case_sub_type"]
            self.fields["archive_sub_type"].initial = initial_values.get("archive_sub_type", "")
            self.fields["contract_types_field"].initial = initial_values["contract_types_field"]
            self.fields["case_types_field"].initial = initial_values["case_types_field"]
            self.fields["case_stage_field"].initial = initial_values["case_stage_field"]
            self.fields["legal_statuses_field"].initial = initial_values["legal_statuses_field"]
            self.fields["legal_status_match_mode"].initial = initial_values["legal_status_match_mode"]
            self.fields["existing_file"].initial = initial_values["existing_file"]

            # 加载适用机构
            institutions = self.instance.applicable_institutions or []
            self.fields["applicable_institutions_field"].initial = json.dumps(institutions, ensure_ascii=False)

            if initial_values["file_path"] == "":
                self.initial["file_path"] = ""

    def clean(self) -> Any:  # pragma: no cover
        """验证文件选择逻辑和模板类型逻辑"""
        cleaned_data = super().clean() or {}
        existing_file = cleaned_data.get("existing_file")
        uploaded_file = cleaned_data.get("file")
        file_path = cleaned_data.get("file_path")
        template_type = cleaned_data.get("template_type")
        contract_sub_type = cleaned_data.get("contract_sub_type")
        case_sub_type = cleaned_data.get("case_sub_type")
        archive_sub_type = cleaned_data.get("archive_sub_type")
        case_stage_field = cleaned_data.get("case_stage_field")

        admin_service = _get_admin_service()
        is_editing = self.instance and self.instance.pk
        original_template_type = self.instance.template_type if is_editing else None

        # 验证文件来源
        file_result = admin_service.validate_file_sources(
            existing_file, uploaded_file, file_path, self.instance, is_editing
        )

        if not file_result["is_valid"]:
            raise forms.ValidationError(file_result["error"])

        # 如果跳过文件验证(编辑模式且未修改文件)
        if file_result.get("skip_file_validation"):
            # 仅验证模板类型
            type_result = admin_service.validate_template_type(
                template_type=template_type,
                contract_sub_type=contract_sub_type,
                case_sub_type=case_sub_type,
                archive_sub_type=archive_sub_type,
                is_editing=is_editing,
                original_template_type=original_template_type,
            )
            if not type_result["is_valid"]:
                raise forms.ValidationError(type_result["errors"])
            cleaned_data["contract_sub_type"] = type_result["contract_sub_type"]
            cleaned_data["case_sub_type"] = type_result["case_sub_type"]
            cleaned_data["archive_sub_type"] = type_result["archive_sub_type"]
            return cleaned_data

        # 更新cleaned_data
        cleaned_data["file_path"] = file_result["cleaned_data"]["file_path"]
        cleaned_data["file"] = file_result["cleaned_data"]["file"]
        cleaned_data["existing_file"] = file_result["cleaned_data"]["existing_file"]

        # 验证模板类型
        type_result = admin_service.validate_template_type(
            template_type=template_type,
            contract_sub_type=contract_sub_type,
            case_sub_type=case_sub_type,
            archive_sub_type=archive_sub_type,
            is_editing=is_editing,
            original_template_type=original_template_type,
        )
        if not type_result["is_valid"]:
            raise forms.ValidationError(type_result["errors"])
        cleaned_data["contract_sub_type"] = type_result["contract_sub_type"]
        cleaned_data["case_sub_type"] = type_result["case_sub_type"]
        cleaned_data["archive_sub_type"] = type_result["archive_sub_type"]

        if template_type == DocumentTemplateType.CASE and not case_stage_field:
            self.add_error("case_stage_field", "请选择案件阶段")

        return cleaned_data

    def save(self, commit: bool = True) -> Any:  # pragma: no cover
        """保存时将多选字段值写入JSON字段,根据模板类型处理相应字段"""
        instance = super().save(commit=False)

        admin_service = _get_admin_service()
        save_data = admin_service.prepare_save_data(
            template_type=self.cleaned_data.get("template_type"),
            contract_sub_type=self.cleaned_data.get("contract_sub_type"),
            case_sub_type=self.cleaned_data.get("case_sub_type"),
            archive_sub_type=self.cleaned_data.get("archive_sub_type"),
            contract_types_field=self.cleaned_data.get("contract_types_field", []),
            case_types_field=self.cleaned_data.get("case_types_field", []),
            case_stage_field=self.cleaned_data.get("case_stage_field", ""),
            legal_statuses_field=self.cleaned_data.get("legal_statuses_field", []),
            legal_status_match_mode=self.cleaned_data.get("legal_status_match_mode", LegalStatusMatchMode.ANY),
            file=self.cleaned_data.get("file"),
            file_path=self.cleaned_data.get("file_path"),
        )

        instance.template_type = save_data["template_type"]
        instance.contract_sub_type = save_data["contract_sub_type"]
        instance.case_sub_type = save_data["case_sub_type"]
        instance.archive_sub_type = save_data["archive_sub_type"]
        instance.contract_types = save_data["contract_types"]
        instance.case_types = save_data["case_types"]
        instance.case_stages = save_data["case_stages"]
        instance.legal_statuses = save_data["legal_statuses"]
        instance.legal_status_match_mode = save_data["legal_status_match_mode"]

        # 保存适用机构
        raw = self.cleaned_data.get("applicable_institutions_field", "")
        try:
            institutions = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            institutions = []
        instance.applicable_institutions = institutions if isinstance(institutions, list) else []

        # 确保file和file_path互斥
        if save_data["file"]:
            instance.file_path = ""
        elif save_data["file_path"]:
            instance.file = ""

        if commit:
            instance.save()
        return instance


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(TemplateAdminViewsMixin, TemplateAdminDisplayMixin, admin.ModelAdmin):  # pragma: no cover
    """
    文书模板管理

    提供文书模板的 CRUD 操作,显示占位符列表并高亮未定义的占位符.
    """

    form = DocumentTemplateForm

    list_display = (
        "id",
        "name",
        "template_type_display",
        "file_location_display",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "template_type",
        "is_active",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = ("-id",)

    readonly_fields = (
        "current_file_display",
        "placeholder_preview",
        "placeholders_display",
        "undefined_placeholders_display",
    )

    fieldsets = (
        (None, {"fields": ("name",)}),
        (
            "模板类型",
            {
                "fields": ("template_type", "contract_sub_type", "case_sub_type", "archive_sub_type"),
                "description": "先选择模板类型(合同/案件/归档),再选择对应的子类型",
            },
        ),
        (
            "适用范围",
            {
                "fields": (
                    "contract_types_field",
                    "case_types_field",
                    "case_stage_field",
                    "legal_statuses_field",
                    "legal_status_match_mode",
                    "applicable_institutions_field",
                ),
                "description": "根据模板类型选择相应的适用范围",
            },
        ),
        (
            "文件",
            {
                "fields": ("current_file_display", "existing_file", "file", "file_path"),
                "description": "三选一:从模板库选择已有文件(不复制)、上传新文件(复制到用户自定义模板目录)、或手动输入路径",
            },
        ),
        (
            "替换词预览",
            {
                "fields": ("placeholder_preview",),
            },
        ),
        (
            "占位符信息",
            {
                "fields": ("placeholders_display", "undefined_placeholders_display"),
                "classes": ("collapse",),
                "description": "模板中使用的占位符列表",
            },
        ),
    )

    # 编辑时追加「状态」fieldset
    _edit_fieldsets: tuple[str, dict[str, Any]] = ("状态", {"fields": ("is_active",)})

    inlines = [DocumentTemplateFolderBindingInline]

    def get_fieldsets(self, request: Any, obj: Any = None) -> list[Any]:  # pragma: no cover
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj is not None:
            fieldsets.insert(len(fieldsets) - 1, self._edit_fieldsets)  # type: ignore[arg-type]
        return fieldsets

    change_list_template = "admin/documents/documenttemplate/change_list.html"

    actions = [
        "activate_templates",
        "deactivate_templates",
        "refresh_placeholders",
        "duplicate_templates",
    ]

    class Media:  # pragma: no cover
        css = {
            LegalStatusMatchMode.ALL: (
                "documents/css/multi_select.css",
                "cases/css/autocomplete.css",
                "documents/css/institution_tags.css",
            )
        }
        js = (
            "cases/js/autocomplete.js",
            "documents/js/template_type_toggle.js",
            "documents/js/institution_tags.js",
        )

    def get_search_results(self, request: Any, queryset: Any, search_term: str) -> tuple[Any, bool]:  # pragma: no cover
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.GET.get("field_name") == "export_template":
            queryset = queryset.filter(
                is_active=True,
                template_type=DocumentTemplateType.CASE,
                case_sub_type=DocumentCaseFileSubType.EVIDENCE_MATERIALS,
            )
        return queryset, use_distinct

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:  # pragma: no cover
        """重写changelist视图，添加初始化按钮"""
        from django.urls import reverse

        extra_context = extra_context or {}
        extra_context["initialize_url"] = reverse("admin:documents_documenttemplate_initialize")
        extra_context.update(self._get_docx_root_extra_context())
        return super().changelist_view(request, extra_context=extra_context)

    @staticmethod
    def _build_llm_model_choices() -> list[tuple[str, str]]:  # pragma: no cover
        """构建 LLM 模型选项列表（复用 legal_research 的模式）。"""
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.model_list_service import ModelListService

        choices: list[tuple[str, str]] = [("", "使用系统默认模型")]
        seen: set[str] = set()

        def append_choice(model_id: str, *, label: str | None = None) -> None:  # pragma: no cover
            value = model_id.strip()
            if not value or value in seen:
                return
            seen.add(value)
            choices.append((value, label or value))

        default_model = LLMConfig.get_openai_compatible_model().strip()
        if default_model:
            append_choice(default_model, label=f"{default_model}（系统默认）")

        try:
            result = ModelListService().get_result()
            for item in result.models:
                model_id = str(item.get("id", "")).strip()
                model_name = str(item.get("name", "")).strip()
                if model_name and model_name != model_id:
                    append_choice(model_id, label=f"{model_name} ({model_id})")
                else:
                    append_choice(model_id)
        except Exception:
            logger.exception("加载模型列表失败")

        if len(choices) == 1:
            append_choice(default_model or "Qwen/Qwen2.5-7B-Instruct")

        return choices

    def changeform_view(  # pragma: no cover
        self,
        request: Any,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        extra_context = extra_context or {}
        extra_context.update(self._get_docx_root_extra_context())
        extra_context["smart_fill_llm_models"] = self._build_llm_model_choices()
        return super().changeform_view(request, object_id=object_id, form_url=form_url, extra_context=extra_context)

    def save_model(self, request: Any, obj: DocumentTemplate, form: Any, change: bool) -> None:  # pragma: no cover
        """保存模型时的额外处理"""
        super().save_model(request, obj, form, change)
