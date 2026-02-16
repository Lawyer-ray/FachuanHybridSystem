"""
法律文书生成系统 - 文件夹模板模型

本模块定义文件夹模板相关的数据模型.
"""

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import DocumentCaseStage, DocumentCaseType, DocumentContractType, FolderTemplateType


class FolderTemplate(models.Model):
    """
    文件夹模板

    定义不同案件类型和阶段所需的文件夹结构.
    结构以 JSON 格式存储,支持无限层级嵌套.

    Requirements: 1.1, 1.3, 7.1
    """

    id: int

    class LegalStatusMatchMode(models.TextChoices):
        """诉讼地位匹配模式"""

        ANY = "any", _("任意匹配")
        ALL = "all", _("全部包含")
        EXACT = "exact", _("完全一致")

    name = models.CharField(max_length=100, verbose_name=_("模板名称"))
    template_type = models.CharField(
        max_length=20,
        choices=FolderTemplateType.choices,
        verbose_name=_("模板类型"),
        help_text=_("选择此模板用于合同还是案件"),
    )
    case_types = models.JSONField(
        default=list, verbose_name=_("案件类型"), help_text=_("JSON 数组,如 ['civil', 'criminal'],支持多选")
    )
    case_stages = models.JSONField(
        default=list, verbose_name=_("案件阶段"), help_text=_("JSON 数组,如 ['first_trial', 'second_trial'],支持多选")
    )
    contract_types = models.JSONField(
        default=list, verbose_name=_("合同类型"), help_text=_("JSON 数组,如 ['civil', 'criminal'],支持多选")
    )
    legal_statuses = models.JSONField(
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
    structure = models.JSONField(default=dict, verbose_name=_("文件夹结构"), help_text=_("JSON 格式的文件夹层级结构"))
    is_default = models.BooleanField(default=False, verbose_name=_("是否默认模板"))
    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label: str = "documents"
        verbose_name = _("文件夹模板")
        verbose_name_plural = _("文件夹模板")
        ordering: ClassVar = ["-updated_at"]
        indexes: ClassVar = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_default"]),
        ]

    def __str__(self) -> None:
        template_type_display = dict(FolderTemplateType.choices).get(self.template_type, self.template_type)
        case_types_display = self._get_types_display(self.case_types, DocumentCaseType)
        return f"{self.name} ({template_type_display} - {case_types_display})"

    def _get_types_display(self, types_list, choices_class) -> str:
        """获取类型列表的显示文本"""
        if not types_list:
            return "-"  # 空值显示为"-"而非"通用"
        if len(types_list) == 1:
            return dict(choices_class.choices).get(types_list[0], types_list[0])
        return f"{len(types_list)}种类型"

    @property
    def template_type_display(self) -> str:
        """模板类型显示"""
        return dict(FolderTemplateType.choices).get(self.template_type, self.template_type)

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

    @property
    def case_type(self) -> None:
        values = self.case_types or []
        return values[0] if values else None

    @property
    def case_stage(self) -> Any:
        values = self.case_stages or []
        return values[0] if values else None

    def get_legal_statuses_display(self) -> str:
        """获取诉讼地位的显示文本"""
        from apps.core.enums import LegalStatus

        choices = dict(LegalStatus.choices)
        statuses = self.legal_statuses or []
        labels = [str(choices.get(code, code)) for code in statuses]
        return "、".join([x for x in labels if x])

    @property
    def legal_statuses_display(self) -> str:
        """诉讼地位显示属性"""
        return self.get_legal_statuses_display() or "-"

    def delete(self, *args, **kwargs) -> None:
        result = super().delete(*args, **kwargs)
        from apps.core.infrastructure import CacheKeys, CacheTimeout, bump_cache_version

        bump_cache_version(CacheKeys.documents_matching_version_folder_templates(), timeout=CacheTimeout.get_day())
        return result
