"""Module for finance."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract


class LogLevel(models.TextChoices):
    INFO = "INFO", _("信息")
    WARN = "WARN", _("预警")
    ERROR = "ERROR", _("错误")


class ContractFinanceLog(models.Model):
    id: int
    contract_id: int
    actor_id: int
    contract: Contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="finance_logs", verbose_name=_("合同")
    )
    action: str = models.CharField(max_length=64, verbose_name=_("动作"))
    level: str = models.CharField(
        max_length=16, choices=LogLevel.choices, default=LogLevel.INFO, verbose_name=_("级别")
    )
    actor: Any = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="finance_logs", verbose_name=_("操作者")
    )
    payload: dict[str, Any] | None = models.JSONField(default=dict, blank=True, verbose_name=_("数据"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("财务日志")
        verbose_name_plural = _("财务日志")
        indexes: ClassVar = [
            models.Index(fields=["contract", "created_at"]),
            models.Index(fields=["level"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.action}-{self.level}"
