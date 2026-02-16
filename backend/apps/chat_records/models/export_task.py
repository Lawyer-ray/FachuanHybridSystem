"""Module for export task."""

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ExportStatus, ExportType


def _export_upload_to(instance: Any, filename: str) -> str:
    return f"chat_records/exports/{instance.project_id}/{instance.id}/{filename}"


class ChatRecordExportTask(models.Model):
    id: Any = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project: Any = models.ForeignKey(
        "ChatRecordProject",
        on_delete=models.CASCADE,
        related_name="export_tasks",
        verbose_name=_("项目"),
    )
    export_type: Any = models.CharField(max_length=16, choices=ExportType.choices, verbose_name=_("导出类型"))
    layout: Any = models.JSONField(default=dict, blank=True, verbose_name=_("版式配置"))
    status: Any = models.CharField(
        max_length=16,
        choices=ExportStatus.choices,
        default=ExportStatus.PENDING,
        verbose_name=_("状态"),
    )
    progress: Any = models.PositiveIntegerField(default=0, verbose_name=_("进度百分比"))
    current: Any = models.PositiveIntegerField(default=0, verbose_name=_("当前项"))
    total: Any = models.PositiveIntegerField(default=0, verbose_name=_("总项"))
    message: Any = models.CharField(max_length=255, blank=True, verbose_name=_("进度信息"))
    error: Any = models.TextField(blank=True, verbose_name=_("错误信息"))
    output_file: Any = models.FileField(upload_to=_export_upload_to, null=True, blank=True, verbose_name=_("导出文件"))
    started_at: Any = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at: Any = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: Any = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("聊天记录导出任务")
        verbose_name_plural = _("聊天记录导出任务")
        indexes: ClassVar = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}-{self.export_type}-{self.id}"
