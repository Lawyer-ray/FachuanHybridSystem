"""Models for document recognition."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentRecognitionStatus(models.TextChoices):
    """文书识别任务状态。"""

    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("识别中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class DocumentRecognitionTool(models.Model):
    """Admin entry model for document recognition."""

    id: int
    name: str = models.CharField(max_length=64, default="Document Recognition")

    class Meta:
        managed = False
        verbose_name = _("文书智能识别")
        verbose_name_plural = _("文书智能识别")


class DocumentRecognitionTask(models.Model):
    """文书识别任务。"""

    id: int
    file_path: str = models.CharField(max_length=1024, verbose_name=_("文件路径"))
    original_filename: str = models.CharField(max_length=256, verbose_name=_("原始文件名"))
    status: str = models.CharField(
        max_length=32,
        choices=DocumentRecognitionStatus.choices,
        default=DocumentRecognitionStatus.PENDING,
        verbose_name=_("任务状态"),
    )
    document_type: str | None = models.CharField(max_length=32, null=True, blank=True, verbose_name=_("文书类型"))
    case_number: str | None = models.CharField(max_length=128, null=True, blank=True, verbose_name=_("案号"))
    key_time: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("关键时间"))
    confidence: float | None = models.FloatField(null=True, blank=True, verbose_name=_("置信度"))
    extraction_method: str | None = models.CharField(max_length=32, null=True, blank=True, verbose_name=_("提取方式"))
    raw_text: str | None = models.TextField(null=True, blank=True, verbose_name=_("原始文本"))
    renamed_file_path: str | None = models.CharField(max_length=1024, null=True, blank=True, verbose_name=_("重命名后路径"))
    binding_success: bool | None = models.BooleanField(null=True, verbose_name=_("绑定成功"))
    case: Any = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("关联案件"),
    )
    case_log: Any = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("案件日志"),
    )
    binding_message: str | None = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("绑定消息"))
    binding_error_code: str | None = models.CharField(max_length=64, null=True, blank=True, verbose_name=_("绑定错误码"))
    error_message: str | None = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    notification_sent: bool = models.BooleanField(default=False, verbose_name=_("通知已发送"))
    notification_sent_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("通知发送时间"))
    notification_error: str | None = models.TextField(null=True, blank=True, verbose_name=_("通知错误信息"))
    notification_file_sent: bool = models.BooleanField(default=False, verbose_name=_("文件已发送"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    started_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        managed = False
        db_table = "automation_documentrecognitiontask"
        verbose_name = _("文书识别任务")
        verbose_name_plural = _("文书识别任务")
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"识别任务 #{self.id} - {self.get_status_display()}"
