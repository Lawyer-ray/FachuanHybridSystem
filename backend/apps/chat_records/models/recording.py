"""Module for recording."""

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ExtractStatus, ExtractStrategy


def _recording_upload_to(instance: Any, filename: str) -> str:
    return f"chat_records/recordings/{instance.project_id}/{instance.id}/{filename}"


class ChatRecordRecording(models.Model):
    id: Any = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project: Any = models.ForeignKey(
        "ChatRecordProject",
        on_delete=models.CASCADE,
        related_name="recordings",
        verbose_name=_("项目"),
    )
    video: Any = models.FileField(upload_to=_recording_upload_to, verbose_name=_("录屏文件"))
    original_name: Any = models.CharField(max_length=255, blank=True, verbose_name=_("原始文件名"))
    size_bytes: Any = models.BigIntegerField(default=0, verbose_name=_("文件大小(字节)"))
    duration_seconds: Any = models.FloatField(null=True, blank=True, verbose_name=_("时长(秒)"))

    extract_status: Any = models.CharField(
        max_length=16,
        choices=ExtractStatus.choices,
        default=ExtractStatus.PENDING,
        verbose_name=_("抽帧状态"),
    )
    extract_strategy: Any = models.CharField(
        max_length=16,
        choices=ExtractStrategy.choices,
        default=ExtractStrategy.INTERVAL,
        verbose_name=_("抽帧策略"),
    )
    extract_dedup_threshold: Any = models.IntegerField(null=True, blank=True, verbose_name=_("抽帧去重阈值"))
    extract_ocr_similarity_threshold: Any = models.FloatField(null=True, blank=True, verbose_name=_("OCR 相似度阈值"))
    extract_ocr_min_new_chars: Any = models.IntegerField(null=True, blank=True, verbose_name=_("OCR 新增字符阈值"))
    extract_cancel_requested: Any = models.BooleanField(default=False, verbose_name=_("请求取消抽帧"))
    extract_progress: Any = models.PositiveIntegerField(default=0, verbose_name=_("抽帧进度百分比"))
    extract_current: Any = models.PositiveIntegerField(default=0, verbose_name=_("抽帧当前项"))
    extract_total: Any = models.PositiveIntegerField(default=0, verbose_name=_("抽帧总项"))
    extract_message: Any = models.CharField(max_length=255, blank=True, verbose_name=_("抽帧进度信息"))
    extract_error: Any = models.TextField(blank=True, verbose_name=_("抽帧错误信息"))
    extract_started_at: Any = models.DateTimeField(null=True, blank=True, verbose_name=_("抽帧开始时间"))
    extract_finished_at: Any = models.DateTimeField(null=True, blank=True, verbose_name=_("抽帧完成时间"))

    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: Any = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("聊天记录录屏")
        verbose_name_plural = _("聊天记录录屏")
        indexes: ClassVar = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["extract_status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}-{self.id}"
