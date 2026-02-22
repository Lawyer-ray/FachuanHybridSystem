"""Module for screenshot."""

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ScreenshotSource


def _screenshot_upload_to(instance: Any, filename: str) -> str:
    return f"chat_records/screenshots/{instance.project_id}/{instance.id}/{filename}"


class ChatRecordScreenshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "ChatRecordProject",
        on_delete=models.CASCADE,
        related_name="screenshots",
        verbose_name=_("项目"),
    )
    image = models.ImageField(upload_to=_screenshot_upload_to, verbose_name=_("截图"))
    ordering = models.PositiveIntegerField(default=0, verbose_name=_("顺序"))
    title = models.CharField(max_length=255, blank=True, verbose_name=_("标题"))
    note = models.TextField(blank=True, verbose_name=_("备注"))
    capture_time_seconds = models.FloatField(null=True, blank=True, verbose_name=_("截图时间点(秒)"))
    sha256 = models.CharField(max_length=64, blank=True, db_index=True, verbose_name=_("内容哈希"))
    dhash = models.CharField(max_length=16, blank=True, db_index=True, verbose_name=_("感知哈希"))
    frame_score = models.FloatField(null=True, blank=True, verbose_name=_("帧评分"))
    source = models.CharField(
        max_length=16, choices=ScreenshotSource.choices, default=ScreenshotSource.UNKNOWN, verbose_name=_("来源")
    )
    is_filtered = models.BooleanField(default=False, verbose_name=_("已过滤"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("聊天记录截图")
        verbose_name_plural = _("聊天记录截图")
        ordering: ClassVar = ["ordering", "created_at"]
        indexes: ClassVar = [
            models.Index(fields=["project", "ordering"]),
            models.Index(fields=["project", "dhash"]),
            models.Index(fields=["project", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}-{self.id}"
