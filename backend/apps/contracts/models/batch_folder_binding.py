"""合同批量绑定文件夹相关模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseType


class ContractTypeFolderRootPreset(models.Model):
    """按合同类型保存默认根目录。"""

    id: int
    case_type = models.CharField(
        max_length=32,
        choices=CaseType.choices,
        unique=True,
        verbose_name=_("合同类型"),
    )
    root_path = models.CharField(
        max_length=1000,
        verbose_name=_("根目录"),
        help_text=_("该合同类型下用于自动匹配的根目录"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("合同类型根目录预设")
        verbose_name_plural = _("合同类型根目录预设")
        indexes: ClassVar = [models.Index(fields=["case_type"])]

    def __str__(self) -> str:
        return f"{self.get_case_type_display()} - {self.root_path}"
