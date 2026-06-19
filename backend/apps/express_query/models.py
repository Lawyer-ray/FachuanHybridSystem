# mypy: disable-error-code=var-annotated
from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.core.filesystem.upload_paths import DatedUUIDPath, MediaEntity


def _waybill_upload_to(_instance: ExpressQueryTask, filename: str) -> str:
    """Deprecated: 保留用于旧 migration 兼容，新代码请使用 DatedUUIDPath。"""
    extension = Path(filename).suffix.lower()
    return f"express_query/waybills/{uuid.uuid4().hex}{extension}"


def _result_pdf_upload_to(_instance: ExpressQueryTask, filename: str) -> str:
    """Deprecated: 保留用于旧 migration 兼容，新代码请使用 DatedUUIDPath。"""
    extension = Path(filename).suffix.lower() or ".pdf"
    return f"express_query/results/{uuid.uuid4().hex}{extension}"


class ExpressQueryTool(models.Model):
    id: int
    name = models.CharField(max_length=64, default="Express Query")

    class Meta:
        managed = False
        verbose_name = "查询EMS/顺丰"
        verbose_name_plural = "查询EMS/顺丰"


class ExpressCarrierType(models.TextChoices):
    UNKNOWN = "unknown", "未知"
    EMS = "ems", "EMS"
    SF = "sf", "顺丰"


class ExpressQueryTaskStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    OCR_PARSING = "ocr_parsing", "OCR识别中"
    WAITING_LOGIN = "waiting_login", "等待登录"
    QUERYING = "querying", "查询中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ExpressQueryTask(models.Model):
    id: int
    title = models.CharField(max_length=255, blank=True, default="", verbose_name="任务名称")
    waybill_image = models.FileField(
        upload_to=DatedUUIDPath(MediaEntity.EXPRESS_QUERY_WAYBILLS), blank=True, null=True, verbose_name="邮单页面"
    )
    status = models.CharField(
        max_length=32,
        choices=ExpressQueryTaskStatus.choices,
        default=ExpressQueryTaskStatus.PENDING,
        verbose_name="任务状态",
    )
    carrier_type = models.CharField(
        max_length=16,
        choices=ExpressCarrierType.choices,
        default=ExpressCarrierType.UNKNOWN,
        verbose_name="承运商",
    )
    tracking_number = models.CharField(max_length=64, blank=True, default="", verbose_name="运单号")
    ocr_text = models.TextField(blank=True, default="", verbose_name="OCR文本")
    query_url = models.URLField(blank=True, default="", verbose_name="查询页面URL")
    result_pdf = models.FileField(
        upload_to=DatedUUIDPath(MediaEntity.EXPRESS_QUERY_RESULTS), blank=True, null=True, verbose_name="查询结果PDF"
    )
    result_payload = models.JSONField(default=dict, blank=True, verbose_name="执行结果")
    queue_task_id = models.CharField(max_length=64, blank=True, default="", verbose_name="队列任务ID")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="express_query_tasks",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(blank=True, null=True, verbose_name="完成时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "快递查询任务"
        verbose_name_plural = "快递查询任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["carrier_type", "-created_at"]),
            models.Index(fields=["tracking_number"]),
        ]

    def __str__(self) -> str:
        reference = self.tracking_number or self.title or str(self.id)
        return f"{self.status} - {reference}"
