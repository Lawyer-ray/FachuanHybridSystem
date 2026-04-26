"""Module for archive classification rule."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    pass


class RuleSource(models.TextChoices):
    """规则来源"""

    LEARNED = "learned", _("自动学习")
    MANUAL = "manual", _("手动添加")


class ArchiveClassificationRule(models.Model):
    """归档分类学习规则 - 从已归档材料中学习到的文件名关键词→归档清单项映射。"""

    id: int
    archive_category: models.CharField = models.CharField(
        max_length=32,
        verbose_name=_("归档分类"),
        help_text=_("non_litigation / litigation / criminal"),
    )
    filename_keyword: models.CharField = models.CharField(
        max_length=100,
        verbose_name=_("文件名关键词"),
        help_text=_("从文件名中提取的关键词"),
    )
    archive_item_code: models.CharField = models.CharField(
        max_length=20,
        verbose_name=_("归档清单编号"),
        help_text=_("目标归档清单项编号，如 'lt_7'、'cr_14'"),
    )
    hit_count: models.PositiveIntegerField = models.PositiveIntegerField(
        default=1,
        verbose_name=_("命中次数"),
        help_text=_("学习到该规则的次数"),
    )
    source: models.CharField = models.CharField(
        max_length=10,
        choices=RuleSource.choices,
        default=RuleSource.LEARNED,
        verbose_name=_("规则来源"),
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间"),
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间"),
    )

    class Meta:
        verbose_name = _("归档分类学习规则")
        verbose_name_plural = _("归档分类学习规则")
        unique_together: ClassVar = [("archive_category", "filename_keyword")]
        indexes: ClassVar = [
            models.Index(fields=["archive_category", "filename_keyword"]),
        ]

    def __str__(self) -> str:
        return f"{self.archive_category}::{self.filename_keyword} → {self.archive_item_code}"
