"""合同绑定文件夹扫描会话模型。"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract


class ContractFolderScanStatus(models.TextChoices):
    PENDING = "pending", _("待执行")
    RUNNING = "running", _("扫描中")
    CLASSIFYING = "classifying", _("分类中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    IMPORTED = "imported", _("已导入")
    CANCELLED = "cancelled", _("已取消")


class ContractFolderScanSession(models.Model):
    """合同自动捕获扫描会话。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="folder_scan_sessions",
        verbose_name=_("合同"),
    )
    status = models.CharField(
        max_length=16,
        choices=ContractFolderScanStatus.choices,
        default=ContractFolderScanStatus.PENDING,
        verbose_name=_("状态"),
    )
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name=_("DjangoQ任务ID"))
    progress = models.PositiveIntegerField(default=0, verbose_name=_("进度百分比"))
    current_file = models.CharField(max_length=255, blank=True, default="", verbose_name=_("当前文件"))
    result_payload = models.JSONField(default=dict, blank=True, verbose_name=_("结果载荷"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    started_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_folder_scan_sessions",
        verbose_name=_("发起人"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("合同文件夹扫描会话")
        verbose_name_plural = _("合同文件夹扫描会话")
        indexes: ClassVar = [
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"contract:{self.contract_id} session:{self.id} status:{self.status}"
