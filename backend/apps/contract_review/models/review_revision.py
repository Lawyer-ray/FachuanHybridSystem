"""审查修订条目（结构化落库）。

**为什么必须有这张表**：AI 修订原先只写进 docx 的 Track Changes，前端拿不到
清单——复审工作台要「左栏列建议 + 律师逐条采纳/驳回」，就必须有结构化数据。
docx 里的痕迹是产物，这张表是决策载体。

`kind` 区分两条管线（错别字 / 风险），`status` 记录律师决策；采纳后由
OnlyOffice 编辑器落成修订痕迹，驳回则不动文档。
"""

from __future__ import annotations

import uuid

from django.db import models

from .review_task import ReviewTask


class RevisionKind(models.TextChoices):
    TYPO = "typo", "错别字"
    RISK = "risk", "风险条款"
    FORMAT = "format", "格式"
    # 律师在编辑器里手工改的：从 docx 的 w:ins/w:del 解析回流的条目，
    # 与 AI 建议同构、同栏、同一套采纳/驳回，只是来源不同。
    MANUAL = "manual", "人工修订"


class RevisionSeverity(models.TextChoices):
    HIGH = "high", "高"
    MEDIUM = "medium", "中"
    LOW = "low", "低"


class RevisionStatus(models.TextChoices):
    PENDING = "pending", "待决策"
    ACCEPTED = "accepted", "已采纳"
    REJECTED = "rejected", "已驳回"


class ReviewRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        ReviewTask,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name="审查任务",
    )
    ordinal = models.IntegerField(default=0, verbose_name="序号", help_text="按审查产出顺序，用于稳定排序")
    kind = models.CharField(
        max_length=16,
        choices=RevisionKind.choices,
        default=RevisionKind.RISK,
        verbose_name="类型",
    )
    severity = models.CharField(
        max_length=16,
        choices=RevisionSeverity.choices,
        blank=True,
        default="",
        verbose_name="风险等级",
    )
    title = models.CharField(max_length=200, blank=True, default="", verbose_name="标题")
    original = models.TextField(verbose_name="原文")
    suggested = models.TextField(verbose_name="建议改为")
    reason = models.TextField(blank=True, default="", verbose_name="依据/理由")
    paragraph_index = models.IntegerField(default=-1, verbose_name="段落索引", help_text="-1 表示未能定位")

    status = models.CharField(
        max_length=16,
        choices=RevisionStatus.choices,
        default=RevisionStatus.PENDING,
        verbose_name="决策状态",
    )
    reject_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="驳回理由",
        help_text="可留空；律师填写的理由可用于改进后续审查",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="决策时间")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "审查修订"
        verbose_name_plural = "审查修订"
        ordering = ["ordinal", "created_at"]
        indexes = [
            models.Index(fields=["task", "status"]),
            models.Index(fields=["task", "ordinal"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_id}#{self.ordinal} {self.title or self.original[:20]}"
