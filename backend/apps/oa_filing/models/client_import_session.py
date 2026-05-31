"""Module for client import session."""

from datetime import datetime
from typing import Any, ClassVar

from django.db import models

class ClientImportStatus(models.TextChoices):
    PENDING = "pending", "待开始"
    IN_PROGRESS = "in_progress", "进行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class ClientImportPhase(models.TextChoices):
    PENDING = "pending", "待开始"
    DISCOVERING = "discovering", "查找并发现"
    IMPORTING = "importing", "导入中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class ClientImportSession(models.Model):
    """OA客户导入记录"""

    id: int

    lawyer_id: int
    lawyer: models.ForeignKey[models.Model, models.Model] = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="client_import_sessions",
        verbose_name="发起用户",
    )
    credential_id: int | None
    credential: models.ForeignKey[Any | None, Any] = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.SET_NULL,
        null=True,
        related_name="client_import_sessions",
        verbose_name="OA凭证",
    )
    status: str = models.CharField(  # type: ignore[assignment]
        max_length=16,
        choices=ClientImportStatus.choices,
        default=ClientImportStatus.PENDING,
        verbose_name="状态",
    )
    phase: str = models.CharField(  # type: ignore[assignment]
        max_length=16,
        choices=ClientImportPhase.choices,
        default=ClientImportPhase.PENDING,
        verbose_name="阶段",
    )
    discovered_count: int = models.IntegerField(  # type: ignore[assignment]
        default=0,
        verbose_name="已发现数量",
    )
    total_count: int = models.IntegerField(  # type: ignore[assignment]
        default=0,
        verbose_name="总数量",
    )
    success_count: int = models.IntegerField(  # type: ignore[assignment]
        default=0,
        verbose_name="成功数量",
    )
    skip_count: int = models.IntegerField(  # type: ignore[assignment]
        default=0,
        verbose_name="跳过数量",
    )
    error_message: str = models.TextField(  # type: ignore[assignment]
        blank=True,
        default="",
        verbose_name="错误信息",
    )
    progress_message: str = models.CharField(  # type: ignore[assignment]
        max_length=255,
        blank=True,
        default="",
        verbose_name="进度描述",
    )
    started_at: datetime | None = models.DateTimeField(  # type: ignore[assignment]
        null=True,
        blank=True,
        verbose_name="开始时间",
    )
    completed_at: datetime | None = models.DateTimeField(  # type: ignore[assignment]
        null=True,
        blank=True,
        verbose_name="完成时间",
    )
    created_at: datetime = models.DateTimeField(  # type: ignore[assignment]
        auto_now_add=True,
        verbose_name="创建时间",
    )
    updated_at: datetime = models.DateTimeField(  # type: ignore[assignment]
        auto_now=True,
        verbose_name="更新时间",
    )

    class Meta:
        verbose_name = "客户导入记录"
        verbose_name_plural = "客户导入记录"
        indexes: ClassVar = [
            models.Index(fields=["lawyer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"ClientImportSession #{self.id} - {self.status}"
