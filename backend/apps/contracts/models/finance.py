"""Module for finance."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from .contract import Contract


class LogLevel(models.TextChoices):
    INFO = "INFO", "信息"
    WARN = "WARN", "预警"
    ERROR = "ERROR", "错误"


class ContractFinanceLog(models.Model):
    id: int
    contract_id: int
    actor_id: int
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="finance_logs", verbose_name="合同")
    action = models.CharField(max_length=64, verbose_name="动作")
    level = models.CharField(max_length=16, choices=LogLevel.choices, default=LogLevel.INFO, verbose_name="级别")
    actor = models.ForeignKey(
        "organization.Lawyer", on_delete=models.PROTECT, related_name="finance_logs", verbose_name="操作者"
    )
    payload: Any = models.JSONField(default=dict, blank=True, verbose_name="数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "财务日志"
        verbose_name_plural = "财务日志"
        indexes: ClassVar = [
            models.Index(fields=["contract", "created_at"]),
            models.Index(fields=["level"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_id}-{self.action}-{self.level}"
