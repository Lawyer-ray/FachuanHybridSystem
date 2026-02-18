"""
法律文书生成系统 - Prompt 版本管理模型

本模块定义 LangChain Prompt 模板的版本管理数据模型.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class PromptVersion(models.Model):
    """
    Prompt 版本管理

    用于管理 LangChain Prompt 模板的不同版本,支持版本切换和回滚.
    同一名称只能有一个激活版本.

    Requirements: 5.1
    """

    id: int
    name: str = models.CharField(max_length=100, verbose_name=_("Prompt 名称"), help_text=_("如:complaint, defense"))

    version: str = models.CharField(max_length=50, verbose_name=_("版本号"), help_text=_("如:v1.0, v1.1"))

    template: str = models.TextField(verbose_name=_("模板内容"), help_text=_("LangChain Prompt 模板字符串"))

    is_active: bool = models.BooleanField(
        default=False, verbose_name=_("是否激活"), help_text=_("同一名称只能有一个激活版本")
    )

    description: str = models.TextField(blank=True, verbose_name=_("版本说明"), help_text=_("描述此版本的变更内容"))

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label: str = "documents"
        verbose_name = _("Prompt 版本")
        verbose_name_plural = _("Prompt 版本")
        ordering: ClassVar = ["-created_at"]
        unique_together: ClassVar = [["name", "version"]]
        indexes: ClassVar = [
            models.Index(fields=["name", "is_active"]),
        ]

    def __str__(self) -> str:
        active_mark = " [激活]" if self.is_active else ""
        return f"{self.name} - {self.version}{active_mark}"
