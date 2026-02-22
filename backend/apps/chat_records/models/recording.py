"""Module for recording."""

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ExtractStatus, ExtractStrategy


def _recording_upload_to(instance: Any, filename: str) -> str:
    return f"chat_records/recordings/{instance.project_id}/{instance.id}/{filename}"


class ChatRecordRecording(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "ChatRecordProject",
        on_delete=models.CASCADE,
        related_name="recordings",
        verbose_name=_("项目"),
    )
    video = models.FileField(upload_to=_recording_upload_to, verbose_name=_("录屏文件"))
    original_name = models.CharField(max_length=255, blank=True, verbose_name=_("原始文件名"))
    size_bytes = models.BigIntegerField(default=0, verbose_name=_("文件大小(字节)"))
    duration_seconds = models.FloatField(null=True, blank=True, verbose_name=_("时长(秒)"))

    extract_status = models.CharField(
        max_length=16,
        choices=ExtractStatus.choices,
        default=ExtractStatus.PENDING,
        verbose_name=_("抽帧状态"),
    )
    extract_strategy = models.CharField(
        max_length=16,
        choices=ExtractStrategy.choices,
        default=ExtractStrategy.INTERVAL,
        verbose_name=_("抽帧策略"),
    )
    extract_dedup_threshold = models.IntegerField(null=True, blank=True, verbose_name=_("抽帧去重阈值"))
    extract_ocr_similarity_threshold = models.FloatField(null=True, blank=True, verbose_name=_("OCR 相似度阈值"))
    extract_ocr_min_new_chars = models.IntegerField(null=True, blank=True, verbose_name=_("OCR 新增字符阈值"))
    extract_cancel_requested = models.BooleanField(default=False, verbose_name=_("请求取消抽帧"))
    extract_progress = models.PositiveIntegerField(default=0, verbose_name=_("抽帧进度百分比"))
    extract_current = models.PositiveIntegerField(default=0, verbose_name=_("抽帧当前项"))
    extract_total = models.PositiveIntegerField(default=0, verbose_name=_("抽帧总项"))
    extract_message = models.CharField(max_length=255, blank=True, verbose_name=_("抽帧进度信息"))
    extract_error = models.TextField(blank=True, verbose_name=_("抽帧错误信息"))
    extract_started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("抽帧开始时间"))
    extract_finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("抽帧完成时间"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("聊天记录录屏")
        verbose_name_plural = _("聊天记录录屏")
        indexes: ClassVar = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["extract_status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}-{self.id}"
