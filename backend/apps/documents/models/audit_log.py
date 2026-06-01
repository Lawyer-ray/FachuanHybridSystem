"""
法律文书生成系统 - 审计日志模型

本模块定义模板审计日志相关的数据模型.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

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
        ("folder_template", "文件夹模板"),
        ("document_template", "文件模板"),
        ("placeholder", "替换词"),
        ("generation_config", "生成配置"),
    ]

    content_type = models.CharField(max_length=50, choices=CONTENT_TYPE_CHOICES, verbose_name="对象类型")
    object_id = models.PositiveIntegerField(verbose_name="对象ID")
    object_repr = models.CharField(max_length=500, verbose_name="对象描述")
    action = models.CharField(max_length=20, choices=TemplateAuditAction.choices, verbose_name="操作类型")
    changes: Any = models.JSONField(
        default=dict, blank=True, verbose_name="变更内容", help_text="JSON 格式记录字段变更"
    )
    user = models.ForeignKey(
        "organization.Lawyer", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="操作人"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP地址")
    user_agent = models.CharField(max_length=500, blank=True, verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="操作时间")

    class Meta:
        app_label = "documents"
        verbose_name = "模板审计日志"
        verbose_name_plural = "模板审计日志"
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["action"]),
            models.Index(fields=["user"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_content_type_display()} #{self.object_id} - {self.get_action_display()}"
