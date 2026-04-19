"""
文书模板 Admin 配置

Requirements: 6.1, 2.9, 2.10
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.interfaces import ServiceLocator
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
from apps.documents.storage import (
    PRIVATE_DOCX_ROOT_SETTING,
    get_configured_private_docx_templates_root,
    get_docx_templates_root,
    get_docx_templates_source,
    list_docx_templates_files,
)

logger = logging.getLogger(__name__)


def _get_template_service() -> Any:
    """工厂函数获取模板服务"""
    from apps.documents.services.template.template_service import DocumentTemplateService

    return DocumentTemplateService()


def _get_admin_service() -> Any:
    """工厂函数获取Admin服务"""
    from apps.documents.services.template.document_template.admin_service import DocumentTemplateAdminService

    return DocumentTemplateAdminService()


def _to_django_relative_path(path: Path) -> str:
    """将绝对路径尽量转换为相对 Django 服务目录（backend）的路径。"""
    backend_root = Path(str(getattr(settings, "BASE_DIR", "."))).resolve().parent
    target = path.resolve()
    try:
        return target.relative_to(backend_root).as_posix()
    except ValueError:
        return Path(str(target)).as_posix()


def _normalize_private_docx_root(raw_value: str) -> str:
    """标准化私有模板根目录输入（支持绝对路径或相对 backend 路径）。"""
    normalized = raw_value.strip()
    if not normalized:
        return ""

    candidate = Path(normalized).expanduser()
    if not candidate.is_absolute():
        backend_root = Path(str(getattr(settings, "BASE_DIR", "."))).resolve().parent
        candidate = (backend_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(str(_("模板根目录不存在或不是文件夹")))

    return str(candidate)


def _get_system_config_service() -> Any:
    return ServiceLocator.get_system_config_service()


class DocumentTemplateFolderBindingInline(admin.TabularInline):
    """文书模板文件夹绑定内联"""

    model = DocumentTemplateFolderBinding
    extra = 1
    fields = ("folder_template", "folder_node_id", "folder_node_path", "is_active")
    readonly_fields = ("folder_node_path",)
    autocomplete_fields = ["folder_template"]

    class Media:
        css = {LegalStatusMatchMode.ALL: ("documents/css/folder_binding_inline.css",)}
        js = ("admin/js/jquery.init.js", "documents/js/folder_binding_inline.js")


class DocumentTemplateForm(forms.ModelForm):
    """文书模板表单,包含模板类型和适用范围选择(与文件夹模板保持一致)"""

    # 模板类型单选(必选)
    template_type = forms.ChoiceField(
        choices=DocumentTemplateType.choices,
        widget=forms.RadioSelect,
        label=_("模板类型"),
        help_text=_("选择此模板用于合同、案件还是归档"),
    )

    # 合同子类型单选(仅合同模板时显示)
    contract_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentContractSubType],
        widget=forms.RadioSelect,
        required=False,
        label=_("合同子类型"),
        help_text=_("仅在选择'合同文书模板'时有效,必须选择合同模板或补充协议模板"),
    )

    case_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentCaseFileSubType],
        widget=forms.RadioSelect,
        required=False,
        label=_("案件文件子类型"),
        help_text=_("仅在选择'案件文书模板'时有效,可选择诉状材料、证据材料、授权委托材料等"),
    )

    archive_sub_type = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentArchiveSubType],
        widget=forms.RadioSelect,
        required=False,
        label=_("归档文件子类型"),
        help_text=_("仅在选择'归档文件模板'时有效,可选择案卷封面、结案归档登记表等"),
    )

    # 合同类型多选(仅合同模板时显示)
    contract_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentContractType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("合同类型"),
        help_text=_("仅在选择'合同文书模板'时有效,可多选"),
    )

    # 案件类型多选(仅案件模板时显示)
    case_types_field = forms.MultipleChoiceField(
        choices=[(c.value, c.label) for c in DocumentCaseType],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("案件类型"),
        help_text=_("仅在选择'案件文书模板'时有效,可多选"),
    )

    # 案件阶段单选(仅案件模板时显示)
    case_stage_field = forms.ChoiceField(
        choices=[("", "请选择")] + [(c.value, c.label) for c in DocumentCaseStage],
        widget=forms.Select,
        required=False,
        label=_("案件阶段"),
        help_text=_("仅在选择'案件文书模板'时有效,单选"),
    )

    # 我方诉讼地位多选(仅案件模板时显示)
    legal_statuses_field = forms.MultipleChoiceField(
        choices=LegalStatus.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("我方诉讼地位"),
        help_text=_("可单选或多选;不选表示匹配任意诉讼地位"),
    )

    # 诉讼地位匹配模式单选(仅案件模板时显示)
    legal_status_match_mode = forms.ChoiceField(
        choices=LegalStatusMatchMode.choices,
        widget=forms.RadioSelect,
        required=False,
        initial=LegalStatusMatchMode.ANY,
        label=_("诉讼地位匹配模式"),
    )

    # 适用机构(案件模板时显示)
    applicable_institutions_field = forms.CharField(
        required=False,
        label=_("适用机构"),
        help_text=_("输入机构名称后回车添加,支持搜索法院名称"),
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
        label=_("从模板库选择"),
        help_text=_("从 docx_templates 目录中选择已有的模板文件(不会复制文件)"),
    )

    class Meta:
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

    def clean(self) -> Any:
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
            self.add_error("case_stage_field", _("请选择案件阶段"))

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
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
class DocumentTemplateAdmin(admin.ModelAdmin[DocumentTemplate]):
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
        "placeholders_display",
        "undefined_placeholders_display",
    )

    fieldsets = (
        (None, {"fields": ("name",)}),
        (
            _("模板类型"),
            {
                "fields": ("template_type", "contract_sub_type", "case_sub_type", "archive_sub_type"),
                "description": _("先选择模板类型(合同/案件/归档),再选择对应的子类型"),
            },
        ),
        (
            _("适用范围"),
            {
                "fields": (
                    "contract_types_field",
                    "case_types_field",
                    "case_stage_field",
                    "legal_statuses_field",
                    "legal_status_match_mode",
                    "applicable_institutions_field",
                ),
                "description": _("根据模板类型选择相应的适用范围"),
            },
        ),
        (
            _("文件"),
            {
                "fields": ("current_file_display", "existing_file", "file", "file_path"),
                "description": _(
                    "三选一:从模板库选择已有文件(不复制)、上传新文件(复制到用户自定义模板目录)、或手动输入路径"
                ),
            },
        ),
        (_("状态"), {"fields": ("is_active",)}),
        (
            _("占位符信息"),
            {
                "fields": ("placeholders_display", "undefined_placeholders_display"),
                "classes": ("collapse",),
                "description": _("模板中使用的占位符列表"),
            },
        ),
    )

    inlines = [DocumentTemplateFolderBindingInline]

    change_list_template = "admin/documents/documenttemplate/change_list.html"

    actions = [
        "activate_templates",
        "deactivate_templates",
        "refresh_placeholders",
        "duplicate_templates",
    ]

    class Media:
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

    def get_search_results(self, request: Any, queryset: Any, search_term: str) -> tuple[Any, bool]:
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.GET.get("field_name") == "export_template":
            queryset = queryset.filter(
                is_active=True,
                template_type=DocumentTemplateType.CASE,
                case_sub_type=DocumentCaseFileSubType.EVIDENCE_MATERIALS,
            )
        return queryset, use_distinct

    def get_urls(self) -> list[Any]:
        """添加自定义URL"""
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:pk>/download/",
                self.admin_site.admin_view(self.download_view),
                name="documents_documenttemplate_download",
            ),
            path(
                "initialize-defaults/",
                self.admin_site.admin_view(self.initialize_defaults_view),
                name="documents_documenttemplate_initialize",
            ),
            path(
                "set-docx-root/",
                self.admin_site.admin_view(self.set_docx_root_view),
                name="documents_documenttemplate_set_docx_root",
            ),
        ]
        return custom_urls + urls

    def download_view(self, request: Any, pk: int) -> Any:
        """下载文件视图"""
        from django.http import FileResponse, Http404

        from apps.core.exceptions import NotFoundError

        obj = self.get_object(request, str(pk))
        if not obj:
            raise Http404("模板不存在")

        try:
            service = _get_admin_service()
            file_path, filename = service.download_file(obj)
        except NotFoundError:
            raise Http404("文件不存在")

        response: Any = FileResponse(Path(file_path).open("rb"), as_attachment=True, filename=filename)
        return response

    def initialize_defaults_view(self, request: Any) -> Any:
        """初始化默认文件模板视图"""
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        from apps.documents.services.document_template.init_service import DocumentTemplateInitService

        try:
            init_service = DocumentTemplateInitService()
            result = init_service.initialize_default_templates()
        except Exception as exc:
            logger.exception("初始化默认模板失败")
            messages.error(request, _("初始化失败：%(error)s") % {"error": str(exc)})
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        if not result.get("success", True):
            missing_files = result.get("missing_files", [])
            preview_files = "、".join(str(item) for item in missing_files[:5])
            if len(missing_files) > 5:
                preview_files = f"{preview_files} ..."

            messages.error(
                request,
                _(
                    "初始化失败：缺少 %(count)s 个模板文件，请先补齐当前模板根目录下对应 docx 文件。当前目录：%(root)s。缺失示例：%(files)s"
                )
                % {"count": len(missing_files), "root": get_docx_templates_root(), "files": preview_files or "-"},
            )
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        msg_parts = []
        if result["folder_created"] > 0:
            msg_parts.append(f"文件夹模板 {result['folder_created']} 个")
        if result["doc_created"] > 0:
            msg_parts.append(f"文件模板 {result['doc_created']} 个")
        if result["binding_created"] > 0:
            msg_parts.append(f"绑定关系 {result['binding_created']} 个")

        if msg_parts:
            messages.success(request, f"✅ 初始化成功！创建了：{' | '.join(msg_parts)}")
        else:
            messages.info(request, "ℹ️ 所有数据已存在，无需初始化")

        return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

    def set_docx_root_view(self, request: Any) -> HttpResponseRedirect:
        """在线设置私有模板根目录（为空则切回公用目录）。"""
        from django.contrib import messages
        from django.urls import reverse

        if request.method != "POST":
            messages.error(request, _("仅支持 POST 请求"))
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        raw_value = str(request.POST.get("private_docx_root", "") or "")

        try:
            normalized = _normalize_private_docx_root(raw_value)
            _get_system_config_service().set_value(
                key=PRIVATE_DOCX_ROOT_SETTING,
                value=normalized,
                category="general",
                description="文书模板私有根目录，留空表示使用公用目录",
                is_secret=False,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))
        except Exception as exc:
            logger.exception("更新模板根目录失败")
            messages.error(request, _("更新失败：%(error)s") % {"error": str(exc)})
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        if normalized:
            messages.success(request, _("模板根目录已更新为：%(path)s") % {"path": normalized})
        else:
            messages.success(request, _("已切换为公用模板目录"))

        return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

    def _get_docx_root_extra_context(self) -> dict[str, str]:
        from django.urls import reverse

        source = get_docx_templates_source()
        source_label = _("私有模板目录") if source == "private" else _("公用模板目录")
        private_root_input = get_configured_private_docx_templates_root()
        return {
            "docx_templates_source": source,
            "docx_templates_source_label": str(source_label),
            "docx_templates_root": _to_django_relative_path(get_docx_templates_root()),
            "docx_templates_set_root_url": reverse("admin:documents_documenttemplate_set_docx_root"),
            "docx_templates_private_root_input": private_root_input,
        }

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:
        """重写changelist视图，添加初始化按钮"""
        from django.urls import reverse

        extra_context = extra_context or {}
        extra_context["initialize_url"] = reverse("admin:documents_documenttemplate_initialize")
        extra_context.update(self._get_docx_root_extra_context())
        return super().changelist_view(request, extra_context=extra_context)

    def changeform_view(
        self,
        request: Any,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        extra_context = extra_context or {}
        extra_context.update(self._get_docx_root_extra_context())
        return super().changeform_view(request, object_id=object_id, form_url=form_url, extra_context=extra_context)

    @admin.display(description=_("模板类型"))
    def template_type_display(self, obj: DocumentTemplate) -> str:
        """显示模板类型"""
        return obj.template_type_display

    @admin.display(description=_("合同类型"))
    def contract_types_display(self, obj: DocumentTemplate) -> str:
        """显示合同类型"""
        return obj.contract_types_display

    @admin.display(description=_("案件类型"))
    def case_types_display(self, obj: DocumentTemplate) -> str:
        """显示案件类型"""
        return obj.case_types_display

    @admin.display(description=_("案件阶段"))
    def case_stage_display(self, obj: DocumentTemplate) -> str:
        """显示案件阶段"""
        stages = obj.case_stages or []
        if not stages:
            return "-"
        stage_label = dict(DocumentCaseStage.choices).get(stages[0], stages[0])
        return str(stage_label)

    @admin.display(description=_("当前文件"))
    def current_file_display(self, obj: DocumentTemplate) -> Any:
        """显示当前文件(只读,不可点击)"""
        if not obj.pk:
            return _("新建模板,请上传文件")
        if obj.file:
            absolute_path = obj.file.path if hasattr(obj.file, "path") else str(obj.file)
            return format_html('<span style="color: #2e7d32;" title="{}">📄 {}</span>', absolute_path, obj.file.name)
        elif obj.file_path:
            return format_html(
                '<span style="color: #1565c0;" title="{}">📁 {}</span>', obj.absolute_file_path, obj.file_path
            )
        return format_html('<span style="color: #c62828;">{}</span>', "⚠️ 未设置文件")

    @admin.display(description=_("文件位置"))
    def file_location_display(self, obj: DocumentTemplate) -> Any:
        """显示文件位置,可点击下载"""
        from django.urls import reverse

        if obj.file:
            download_url = reverse("admin:documents_documenttemplate_download", args=[obj.pk])
            absolute_path = obj.file.path if hasattr(obj.file, "path") else str(obj.file)
            return format_html(
                '<a href="{}" title="点击下载 | 绝对路径: {}" target="_blank">📄 {}</a>',
                download_url,
                absolute_path,
                obj.file.name,
            )
        elif obj.file_path:
            download_url = reverse("admin:documents_documenttemplate_download", args=[obj.pk])
            return format_html(
                '<a href="{}" title="点击下载 | 绝对路径: {}" target="_blank">📁 {}</a>',
                download_url,
                obj.absolute_file_path,
                obj.file_path,
            )
        return format_html('<span style="color: #999;">{}</span>', "未设置")

    @admin.display(description=_("占位符"))
    def placeholder_count_display(self, obj: DocumentTemplate) -> Any:
        """显示占位符数量"""
        try:
            service = _get_template_service()
            placeholders = service.extract_placeholders(obj)
            undefined = service.get_undefined_placeholders(obj)

            all_placeholders_text = ", ".join(placeholders) if placeholders else "无占位符"

            if undefined:
                undefined_names = ", ".join(undefined[:3])
                if len(undefined) > 3:
                    undefined_names += f" 等{len(undefined)}个"

                return format_html(
                    '<span style="color: #e65100;" title="所有占位符: {} | 未定义占位符: {}">'
                    "{} ({}个未定义: {})</span>",
                    all_placeholders_text,
                    ", ".join(undefined),
                    len(placeholders),
                    len(undefined),
                    undefined_names,
                )
            else:
                return format_html('<span title="所有占位符: {}">{}</span>', all_placeholders_text, len(placeholders))
        except Exception as e:
            logger.error("提取占位符失败 - 模板ID: %s, 错误: %s", obj.id, e, exc_info=True)
            return format_html('<span style="color: #c62828;" title="{}">错误</span>', str(e))

    @admin.display(description=_("占位符列表"))
    def placeholders_display(self, obj: DocumentTemplate) -> Any:
        """显示占位符列表"""
        if not obj.pk:
            return _("保存后可查看占位符")

        try:
            service = _get_template_service()
            placeholders = service.extract_placeholders(obj)
            undefined = set(service.get_undefined_placeholders(obj))

            admin_service = _get_admin_service()
            return admin_service.render_placeholders_table(placeholders, undefined)
        except Exception as e:
            logger.exception("操作失败")
            return format_html('<span style="color: #c62828;">提取失败: {}</span>', str(e))

    @admin.display(description=_("未定义占位符"))
    def undefined_placeholders_display(self, obj: DocumentTemplate) -> Any:
        """显示未定义的占位符(高亮警告)"""
        if not obj.pk:
            return _("保存后可查看")

        try:
            service = _get_template_service()
            undefined = service.get_undefined_placeholders(obj)

            admin_service = _get_admin_service()
            return admin_service.render_undefined_placeholders_warning(undefined)
        except Exception as e:
            logger.exception("操作失败")
            return format_html('<span style="color: #c62828;">检查失败: {}</span>', str(e))

    def activate_templates(self, request: Any, queryset: Any) -> None:
        """批量启用模板"""
        service = _get_admin_service()
        updated: int = service.batch_activate(queryset)
        self.message_user(request, _("已启用 %(count)d 个模板") % {"count": updated})

    def deactivate_templates(self, request: Any, queryset: Any) -> None:
        """批量禁用模板"""
        service = _get_admin_service()
        updated: int = service.batch_deactivate(queryset)
        self.message_user(request, _("已禁用 %(count)d 个模板") % {"count": updated})

    @admin.action(description=_("刷新占位符信息"))
    def refresh_placeholders(self, request: Any, queryset: Any) -> None:
        """刷新占位符信息(触发重新解析)"""
        count = queryset.count()
        self.message_user(request, _("已刷新 %(count)d 个模板的占位符信息") % {"count": count})

    @admin.action(description=_("复制选中的模板"))
    def duplicate_templates(self, request: Any, queryset: Any) -> None:
        """批量复制文书模板"""
        admin_service = _get_admin_service()
        count = admin_service.batch_duplicate_templates(queryset)
        self.message_user(request, _("已复制 %(count)d 个模板") % {"count": count})

    def save_model(self, request: Any, obj: DocumentTemplate, form: Any, change: bool) -> None:
        """保存模型时的额外处理"""
        super().save_model(request, obj, form, change)
