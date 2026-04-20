"""
法律文书生成系统 - 占位符模型

本模块定义占位符(替换词)相关的数据模型.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_lifecycle import AFTER_CREATE, AFTER_UPDATE, LifecycleModel, hook

logger = logging.getLogger(__name__)


class Placeholder(LifecycleModel):
    """
    替换词

    定义文书模板中的占位符,用于统一管理占位符定义.
    具体的数据替换和格式化由外部脚本实现.

    Requirements: 3.1, 3.4, 7.3
    """

    id: int
    key = models.CharField(
        max_length=100, unique=True, verbose_name=_("占位符键"), help_text=_("模板中使用的占位符名称,如 case_name")
    )
    display_name = models.CharField(max_length=200, verbose_name=_("显示名称"), help_text=_("用于界面显示的友好名称"))
    example_value = models.CharField(
        max_length=200, blank=True, verbose_name=_("示例值"), help_text=_("占位符的示例值,用于说明用途")
    )
    description = models.TextField(blank=True, verbose_name=_("说明"))
    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))

    class Meta:
        app_label = "documents"
        verbose_name = _("替换词")
        verbose_name_plural = _("替换词")
        ordering: ClassVar = ["key"]
        indexes: ClassVar = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.key})"

    @property
    def data_path(self) -> str:
        return getattr(self, "_data_path", "")

    @data_path.setter
    def data_path(self, value: str) -> None:
        self._data_path = value

    @property
    def category(self) -> str:
        return getattr(self, "_category", "")

    @category.setter
    def category(self, value: str) -> None:
        self._category = value

    @hook(AFTER_CREATE)
    def on_create_audit_log(self) -> None:
        """创建时记录审计日志"""
        try:
            from apps.documents.signals import _create_audit_log
            from apps.documents.models.choices import TemplateAuditAction

            _create_audit_log(self, TemplateAuditAction.CREATE, is_new=True)
        except Exception:
            logger.exception("创建审计日志失败: %s", self)

    @hook(AFTER_UPDATE)
    def on_update_audit_log(self) -> None:
        """更新时记录审计日志"""
        try:
            from apps.documents.signals import _create_audit_log, _get_changes_from_lifecycle
            from apps.documents.models.choices import TemplateAuditAction

            changes = _get_changes_from_lifecycle(self, self.__class__)
            if not changes:
                return

            if "is_active" in changes and len(changes) == 1:
                action = TemplateAuditAction.ACTIVATE if self.is_active else TemplateAuditAction.DEACTIVATE
            else:
                action = TemplateAuditAction.UPDATE
            _create_audit_log(self, action, changes)
        except Exception:
            logger.exception("更新审计日志失败: %s", self)
