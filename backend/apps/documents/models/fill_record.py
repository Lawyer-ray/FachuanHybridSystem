"""
批量填充任务与填充记录模型

本模块定义 BatchFillTask (批量填充任务) 和 FillRecord (填充记录) 数据模型,
用于记录外部模板的填充操作历史.

Requirements: 14.6, 15.2, 15.4, 16.5, 18.1, 18.2
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .external_template import ExternalTemplate

logger: logging.Logger = logging.getLogger(__name__)


class BatchFillTask(models.Model):
    """
    批量填充任务

    记录一次批量填充操作的元数据, 包含案件、选择的模板列表、
    操作者、时间、ZIP 文件路径和汇总报告.

    Requirements: 14.6, 16.5
    """

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        verbose_name=_("关联案件"),
        help_text=_("批量填充关联的案件"),
    )
    templates = models.ManyToManyField(
        ExternalTemplate,
        verbose_name=_("选择的模板"),
        help_text=_("本次批量填充选择的外部模板"),
    )
    initiated_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("操作者"),
        related_name="initiated_batch_fill_tasks",
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("发起时间"),
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("完成时间"),
    )
    zip_file_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("ZIP文件路径"),
        help_text=_("批量填充生成的 ZIP 压缩包路径"),
    )
    summary_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("汇总报告"),
        help_text=_("批量填充的汇总报告 JSON"),
    )

    class Meta:
        app_label = "documents"
        verbose_name = _("批量填充任务")
        verbose_name_plural = _("批量填充任务")
        ordering: ClassVar = ["-started_at"]

    def __str__(self) -> str:
        return f"BatchFillTask #{self.id}"


class FillRecord(models.Model):
    """
    填充记录

    记录单次填充操作的历史, 包含案件、模板、当事人、操作者、
    时间、生成文件路径、填充报告和自定义填充值.

    Requirements: 15.2, 15.4, 18.1, 18.2
    """

    id: int
    batch_task = models.ForeignKey(
        BatchFillTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="records",
        verbose_name=_("批量任务"),
        help_text=_("所属的批量填充任务, 单次填充时为空"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        verbose_name=_("关联案件"),
    )
    template = models.ForeignKey(
        ExternalTemplate,
        on_delete=models.CASCADE,
        verbose_name=_("关联模板"),
    )
    party = models.ForeignKey(
        "cases.CaseParty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("关联当事人"),
    )
    filled_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("操作者"),
        related_name="fill_records",
    )
    filled_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("填充时间"),
    )
    file_path = models.CharField(
        max_length=500,
        verbose_name=_("生成文件路径"),
        help_text=_("填充生成的文件相对于 MEDIA_ROOT 的路径"),
    )
    original_output_name = models.CharField(
        max_length=255,
        verbose_name=_("输出文件名"),
        help_text=_("填充生成的文件原始名称"),
    )
    report_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("填充报告"),
        help_text=_("填充操作的详细报告 JSON"),
    )
    custom_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("自定义填充值"),
        help_text=_("用户手动输入的自定义字段值"),
    )
    file_available = models.BooleanField(
        default=True,
        verbose_name=_("文件是否可用"),
        help_text=_("生成的文件是否仍然可访问"),
    )

    class Meta:
        app_label = "documents"
        verbose_name = _("填充记录")
        verbose_name_plural = _("填充记录")
        ordering: ClassVar = ["-filled_at"]
        indexes: ClassVar = [
            models.Index(fields=["case", "-filled_at"]),
            models.Index(fields=["template", "-filled_at"]),
        ]

    def __str__(self) -> str:
        return f"FillRecord #{self.id}"
