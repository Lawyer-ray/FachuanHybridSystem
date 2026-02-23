"""
外部模板模型

本模块定义外部模板 (ExternalTemplate) 数据模型,
用于存储法院、破产管理人等机构提供的 Word 模板文件及其元数据.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import SourceType, TemplateCategory, TemplateStatus

logger: logging.Logger = logging.getLogger(__name__)


class ExternalTemplate(models.Model):
    """
    外部模板

    存储法院、破产管理人、仲裁委员会等机构提供的 Word 模板文件.
    通过结构指纹 (SHA-256) 去重, 支持 LLM 字段映射分析.
    数据隔离基于 law_firm (律所级别共享).

    Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 3.1, 3.4, 8.1, 8.2,
                  9.1, 9.2, 11.4, 11.5, 12.1, 13.1, 13.2, 13.3
    """

    id: int
    name = models.CharField(
        max_length=255,
        verbose_name=_("模板名称"),
    )
    category = models.CharField(
        max_length=50,
        choices=TemplateCategory.choices,
        verbose_name=_("模板类别"),
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        verbose_name=_("来源类型"),
    )
    court = models.ForeignKey(
        "core.Court",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("关联法院"),
        help_text=_("来源类型为法院时关联的法院"),
    )
    organization_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("机构名称"),
        help_text=_("破产管理人、仲裁委员会等机构名称"),
    )
    file_path = models.CharField(
        max_length=500,
        verbose_name=_("文件路径"),
        help_text=_("相对于 MEDIA_ROOT 的存储路径"),
    )
    original_filename = models.CharField(
        max_length=255,
        verbose_name=_("原始文件名"),
    )
    file_size = models.PositiveIntegerField(
        verbose_name=_("文件大小(字节)"),
    )
    structure_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("结构指纹"),
        help_text=_("基于模板 XML 结构计算的 SHA-256 哈希值"),
    )
    structure_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("提取的结构JSON"),
    )
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.UPLOADED,
        verbose_name=_("状态"),
    )
    mapping_source = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("映射来源模板"),
        help_text=_("结构指纹匹配时复用映射的原始模板"),
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name=_("版本号"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("是否活跃"),
    )
    uploaded_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("上传者"),
        related_name="uploaded_external_templates",
    )
    law_firm = models.ForeignKey(
        "organization.LawFirm",
        on_delete=models.CASCADE,
        verbose_name=_("所属律所"),
        related_name="external_templates",
    )
    status_changed_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("状态变更时间"),
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
        app_label = "documents"
        verbose_name = _("外部模板")
        verbose_name_plural = _("外部模板")
        ordering: ClassVar = ["-updated_at"]
        indexes: ClassVar = [
            models.Index(fields=["law_firm", "court", "category"]),
            models.Index(fields=["law_firm", "is_active"]),
            models.Index(fields=["structure_fingerprint"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return self.name
