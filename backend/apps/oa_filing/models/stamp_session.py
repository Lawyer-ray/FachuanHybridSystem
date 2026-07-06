from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class StampSessionStatus(models.TextChoices):
    PENDING = "pending", "待开始"
    IN_PROGRESS = "in_progress", "进行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class StampSession(models.Model):
    """盖章申请执行记录"""

    id: int

    contract: Any = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="stamp_sessions",
        verbose_name="合同",
    )
    credential: Any = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stamp_sessions",
        verbose_name="登录凭证",
    )
    user: Any = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="stamp_sessions",
        verbose_name="发起用户",
    )
    oa_case_number: str = models.CharField(  # type: ignore[assignment]
        max_length=100,
        verbose_name="律所OA案件编号",
    )
    file_path: str = models.CharField(  # type: ignore[assignment]
        max_length=1000,
        verbose_name="上传文件路径",
    )
    status: str = models.CharField(  # type: ignore[assignment]
        max_length=16,
        choices=StampSessionStatus.choices,
        default=StampSessionStatus.PENDING,
        verbose_name="状态",
    )
    error_message: str = models.TextField(  # type: ignore[assignment]
        blank=True,
        default="",
        verbose_name="错误信息",
    )
    created_at: Any = models.DateTimeField(
        auto_now_add=True,
        verbose_name="创建时间",
    )
    updated_at: Any = models.DateTimeField(
        auto_now=True,
        verbose_name="更新时间",
    )

    class Meta:
        verbose_name = "盖章申请记录"
        verbose_name_plural = "盖章申请记录"
        indexes: ClassVar = [
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"StampSession #{self.id} - {self.oa_case_number} - {self.status}"
