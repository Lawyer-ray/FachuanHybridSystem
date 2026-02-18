"""
法律文书生成系统 - 审计日志模型

本模块定义模板审计日志相关的数据模型.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import TemplateAuditAction


class TemplateAuditLog(models.Model):
    """
    模板审计日志

    记录所有模板相关的修改历史,用于审计追踪.

    Requirements: 6.6
    """

    id: int
    user_id: int  # 外键ID字段
    CONTENT_TYPE_CHOICES: ClassVar = [
        ("folder_template", _("文件夹模板")),
        ("document_template", _("文件模板")),
        ("placeholder", _("替换词")),
        ("generation_config", _("生成配置")),
    ]

    content_type: str = models.CharField(max_length=50, choices=CONTENT_TYPE_CHOICES, verbose_name=_("对象类型"))
    object_id: int = models.PositiveIntegerField(verbose_name=_("对象ID"))
    object_repr: str = models.CharField(max_length=500, verbose_name=_("对象描述"))
    action: str = models.CharField(max_length=20, choices=TemplateAuditAction.choices, verbose_name=_("操作类型"))
    changes: dict[str, Any] = models.JSONField(
        default=dict, blank=True, verbose_name=_("变更内容"), help_text=_("JSON 格式记录字段变更")
    )
    user: models.ForeignKey[Any] = models.ForeignKey(
        "organization.Lawyer", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("操作人")
    )
    ip_address: str | None = models.GenericIPAddressField(null=True, blank=True, verbose_name=_("IP地址"))
    user_agent: str = models.CharField(max_length=500, blank=True, verbose_name=_("User Agent"))
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name=_("操作时间"))

    class Meta:
        app_label: str = "documents"
        verbose_name = _("模板审计日志")
        verbose_name_plural = _("模板审计日志")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["action"]),
            models.Index(fields=["user"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_content_type_display()} #{self.object_id} - {self.get_action_display()}"
