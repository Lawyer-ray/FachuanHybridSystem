"""Module for client import session."""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class ClientImportStatus(models.TextChoices):
    PENDING = "pending", _("待开始")
    IN_PROGRESS = "in_progress", _("进行中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class ClientImportPhase(models.TextChoices):
    PENDING = "pending", _("待开始")
    DISCOVERING = "discovering", _("查找并发现")
    IMPORTING = "importing", _("导入中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class ClientImportSession(models.Model):
    """OA客户导入记录"""

    id: int

    lawyer = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="client_import_sessions",
        verbose_name=_("发起用户"),
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.SET_NULL,
        null=True,
        related_name="client_import_sessions",
        verbose_name=_("OA凭证"),
    )
    status = models.CharField(
        max_length=16,
        choices=ClientImportStatus.choices,
        default=ClientImportStatus.PENDING,
        verbose_name=_("状态"),
    )
    phase = models.CharField(
        max_length=16,
        choices=ClientImportPhase.choices,
        default=ClientImportPhase.PENDING,
        verbose_name=_("阶段"),
    )
    discovered_count = models.IntegerField(
        default=0,
        verbose_name=_("已发现数量"),
    )
    total_count = models.IntegerField(
        default=0,
        verbose_name=_("总数量"),
    )
    success_count = models.IntegerField(
        default=0,
        verbose_name=_("成功数量"),
    )
    skip_count = models.IntegerField(
        default=0,
        verbose_name=_("跳过数量"),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("错误信息"),
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("进度描述"),
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("开始时间"),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("完成时间"),
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
        verbose_name = _("客户导入记录")
        verbose_name_plural = _("客户导入记录")
        indexes: ClassVar = [
            models.Index(fields=["lawyer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"ClientImportSession #{self.id} - {self.status}"
