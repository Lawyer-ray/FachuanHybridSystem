from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class OAConfig(models.Model):
    """OA系统配置"""

    id: int

    site_name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_("凭证站点名称"),
        help_text=_("与账号密码管理中的「网站名称」一致，用于自动匹配凭证"),
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name=_("是否启用"),
    )
    field_mapping: Any = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("字段映射规则"),
        help_text=_("本系统字段到OA表单字段的映射"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间"),
    )

    class Meta:
        verbose_name = _("OA系统配置")
        verbose_name_plural = _("OA系统配置")
        indexes: ClassVar = [
            models.Index(fields=["is_enabled"]),
        ]

    def __str__(self) -> str:
        return self.site_name
