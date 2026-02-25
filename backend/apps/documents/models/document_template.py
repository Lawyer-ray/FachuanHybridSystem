"""
法律文书生成系统 - 文件模板模型

本模块定义文件模板相关的数据模型.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.path import Path
from apps.documents.storage import document_template_storage

from .choices import (
    DocumentCaseFileSubType,
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractSubType,
    DocumentContractType,
    DocumentTemplateType,
    LegalStatusMatchMode,
)

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .evidence import EvidenceList


class DocumentTemplate(models.Model):
    """
    文书模板

    基于 docx 格式的法律文书模板文件.
    支持两种模式:文件上传和路径引用.
    支持两种模板类型:单个文书和全套文书.

    Requirements: 2.1, 2.4, 2.6, 7.2
    """

    id: int
    name = models.CharField(max_length=200, verbose_name=_("模板名称"))
    description = models.TextField(blank=True, verbose_name=_("描述"))
    template_type = models.CharField(
        max_length=20,
        choices=DocumentTemplateType.choices,
        default=DocumentTemplateType.CONTRACT,
        verbose_name=_("模板类型"),
        help_text=_("选择此模板用于合同还是案件"),
    )
    contract_sub_type = models.CharField(
        max_length=30,
        choices=DocumentContractSubType.choices,
        blank=True,
        null=True,
        verbose_name=_("合同子类型"),
        help_text=_("仅在选择'合同文件模板'时有效,必须选择合同模板或补充协议模板"),
    )
    case_sub_type = models.CharField(
        max_length=50,
        choices=DocumentCaseFileSubType.choices,
        blank=True,
        null=True,
        verbose_name=_("案件文件子类型"),
        help_text=_("仅在选择'案件文件模板'时有效,可选择诉状材料、证据材料、授权委托材料等"),
    )
    file = models.FileField(
        storage=document_template_storage,
        upload_to="",  # 存储类会自动处理路径
        blank=True,
        null=True,
        verbose_name=_("上传文件"),
    )
    file_path = models.CharField(
        max_length=500, blank=True, verbose_name=_("文件路径"), help_text=_("相对于模板基础目录的路径")
    )
    # 适用范围字段(与文件夹模板保持一致)
    case_types: Any = models.JSONField(
        default=list, verbose_name=_("案件类型"), help_text=_("JSON 数组,如 ['civil', 'criminal'],支持多选")
    )
    case_stages: Any = models.JSONField(
        default=list, verbose_name=_("案件阶段"), help_text=_("JSON 数组,如 ['first_trial', 'second_trial'],支持多选")
    )
    contract_types: Any = models.JSONField(
        default=list, verbose_name=_("合同类型"), help_text=_("JSON 数组,如 ['civil', 'criminal'],支持多选")
    )
    legal_statuses: Any = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("我方诉讼地位"),
        help_text=_("可单选或多选;为空表示匹配任意诉讼地位"),
    )
    legal_status_match_mode = models.CharField(
        max_length=16,
        choices=LegalStatusMatchMode.choices,
        default=LegalStatusMatchMode.ANY,
        verbose_name=_("诉讼地位匹配模式"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    if TYPE_CHECKING:
        folder_bindings: RelatedManager[DocumentTemplateFolderBinding]
        evidence_lists: RelatedManager[EvidenceList]

    class Meta:
        app_label = "documents"
        verbose_name = _("文件模板")
        verbose_name_plural = _("文件模板")
        ordering: ClassVar = ["-updated_at"]
        indexes: ClassVar = [
            models.Index(fields=["template_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        file_present = bool(self.file)
        file_path_present = bool((self.file_path or "").strip())

        if file_present and file_path_present:
            message = _("不能同时提供上传文件和文件路径")
            raise ValidationError({"file": message, "file_path": message})

        if not file_present and not file_path_present:
            raise ValidationError(_("必须提供上传文件或文件路径"))

    def get_file_location(self) -> str:
        """获取文件实际位置"""
        if self.file:
            # 使用自定义存储的文件
            return str(self.file.storage.path(self.file.name))
        elif self.file_path:
            # 使用文件路径引用
            path_obj = Path(self.file_path)
            if path_obj.is_absolute():
                return self.file_path
            else:
                # 相对路径,基于docx_templates目录
                from django.conf import settings

                base_dir = Path(str(getattr(settings, "BASE_DIR", ".")))
                docx_templates_root = base_dir.parent / "apps" / "documents" / "docx_templates"
                return str(docx_templates_root / self.file_path)
        return ""

    def _get_types_display(self, types_list: list[Any], choices_class: type[models.TextChoices]) -> str:
        """获取类型列表的显示文本"""
        if not types_list:
            return "-"
        if len(types_list) == 1:
            return str(dict(choices_class.choices).get(types_list[0], types_list[0]))
        return f"{len(types_list)}种类型"

    @property
    def template_type_display(self) -> str:
        """模板类型显示"""
        base_type = str(dict(DocumentTemplateType.choices).get(self.template_type, self.template_type))
        if self.template_type == DocumentTemplateType.CONTRACT and self.contract_sub_type:
            sub_type = str(dict(DocumentContractSubType.choices).get(self.contract_sub_type, self.contract_sub_type))
            return f"{base_type} - {sub_type}"
        if self.template_type == DocumentTemplateType.CASE and self.case_sub_type:
            sub_type = str(dict(DocumentCaseFileSubType.choices).get(self.case_sub_type, self.case_sub_type))
            return f"{base_type} - {sub_type}"
        return base_type

    @property
    def case_types_display(self) -> str:
        """案件类型显示"""
        return self._get_types_display(self.case_types, DocumentCaseType)

    @property
    def case_stages_display(self) -> str:
        """案件阶段显示"""
        return self._get_types_display(self.case_stages, DocumentCaseStage)

    @property
    def contract_types_display(self) -> str:
        """合同类型显示"""
        return self._get_types_display(self.contract_types, DocumentContractType)

    def get_legal_statuses_display(self) -> str:
        """获取诉讼地位显示文本"""
        from apps.core.enums import LegalStatus

        choices = dict(LegalStatus.choices)
        statuses = self.legal_statuses or []
        labels = [str(choices.get(code, code)) for code in statuses]
        return "、".join([x for x in labels if x]) or "任意"
    @property
    def absolute_file_path(self) -> str:
        """文件的绝对路径"""
        if not self.file_path:
            return ""
        path_obj = Path(self.file_path)
        if path_obj.is_absolute():
            return self.file_path
        return str(path_obj.resolve())



class DocumentTemplateFolderBinding(models.Model):
    """
    文件模板与文件夹节点绑定

    建立文件模板和文件夹模板中具体节点的多对多关系.
    支持:
    - 一个文件模板绑定到多个文件夹模板的不同节点
    - 同一文件夹模板中,一个文件模板可放在不同位置

    Requirements: 2.8
    """

    id: int
    document_template_id: int  # 外键ID字段
    folder_template_id: int  # 外键ID字段
    document_template = models.ForeignKey(
        "documents.DocumentTemplate",
        on_delete=models.CASCADE,
        related_name="folder_bindings",
        verbose_name=_("文件模板"),
    )
    folder_template = models.ForeignKey(
        "documents.FolderTemplate",
        on_delete=models.CASCADE,
        related_name="document_bindings",
        verbose_name=_("文件夹模板"),
    )
    folder_node_id = models.CharField(
        max_length=100,
        verbose_name=_("文件夹节点ID"),
        help_text=_("文件夹结构JSON中的节点ID"),
    )
    folder_node_path = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("文件夹路径"),
        help_text=_("自动计算的文件夹路径,如:一审/1-立案材料/1-起诉状和反诉答辩状"),
    )

    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label = "documents"
        verbose_name = _("文件模板文件夹绑定")
        verbose_name_plural = _("文件模板文件夹绑定")
        ordering: ClassVar = ["folder_template", "document_template"]
        # 同一文件模板在同一文件夹模板的同一节点只能绑定一次
        unique_together: ClassVar = ["document_template", "folder_template", "folder_node_id"]
        indexes: ClassVar = [
            models.Index(fields=["folder_template", "folder_node_id"]),
            models.Index(fields=["document_template"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.document_template.name} → "
            f"{self.folder_template.name}/{self.folder_node_path or self.folder_node_id}"
        )
