from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class SessionStatus(models.TextChoices):
    PENDING = "pending", _("待开始")
    IN_PROGRESS = "in_progress", _("进行中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class FilingSession(models.Model):
    """OA立案执行记录"""

    id: int

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="filing_sessions",
        verbose_name=_("合同"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="filing_sessions",
        verbose_name=_("案件"),
    )
    oa_config = models.ForeignKey(
        "oa_filing.OAConfig",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="filing_sessions",
        verbose_name=_("OA配置"),
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.SET_NULL,
        null=True,
        related_name="filing_sessions",
        verbose_name=_("登录凭证"),
    )
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="filing_sessions",
        verbose_name=_("发起用户"),
    )
    status = models.CharField(
        max_length=16,
        choices=SessionStatus.choices,
        default=SessionStatus.PENDING,
        verbose_name=_("状态"),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("错误信息"),
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
        verbose_name = _("立案记录")
        verbose_name_plural = _("立案记录")
        indexes: ClassVar = [
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"FilingSession #{self.id} - {self.status}"
