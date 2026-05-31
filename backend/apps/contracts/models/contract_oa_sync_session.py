"""合同 OA 信息同步会话模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

class ContractOASyncStatus(models.TextChoices):
    PENDING = "pending", "待执行"
    RUNNING = "running", "执行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class ContractOASyncSession(models.Model):
    """合同 OA 信息批量同步会话。"""

    id: int
    started_by_id: int | None
    status: models.CharField = models.CharField(
        max_length=16,
        choices=ContractOASyncStatus.choices,
        default=ContractOASyncStatus.PENDING,
        verbose_name="状态",
    )
    task_id: models.CharField = models.CharField(max_length=64, blank=True, default="", verbose_name="DjangoQ任务ID")
    total_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="总数")
    processed_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="已处理")
    matched_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="唯一命中")
    multiple_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="多结果")
    not_found_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="未匹配")
    error_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="错误")
    progress_message: models.CharField = models.CharField(
        max_length=255, blank=True, default="", verbose_name="进度信息"
    )
    result_payload: models.JSONField = models.JSONField(default=dict, blank=True, verbose_name="结果载荷")
    error_message: models.TextField = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_by: models.ForeignKey = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_oa_sync_sessions",
        verbose_name="发起人",
    )
    started_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "合同OA同步会话"
        verbose_name_plural = "合同OA同步会话"
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["started_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"contract_oa_sync:{self.pk} status:{self.status}"
