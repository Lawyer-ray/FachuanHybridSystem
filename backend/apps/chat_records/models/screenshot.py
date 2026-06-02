"""Module for screenshot."""

import uuid
from typing import Any, ClassVar

from django.db import models
from django_lifecycle import BEFORE_UPDATE, LifecycleModel, hook

from apps.core.filesystem.upload_paths import EntityIdPath

from .choices import ScreenshotSource


def _screenshot_upload_to(instance: Any, filename: str) -> str:
    """Deprecated: 保留用于旧 migration 兼容，新代码请使用 EntityIdPath。"""
    return f"chat_records/screenshots/{instance.project_id}/{instance.id}/{filename}"


class ChatRecordScreenshot(LifecycleModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "ChatRecordProject",
        on_delete=models.CASCADE,
        related_name="screenshots",
        verbose_name="项目",
    )
    image = models.ImageField(upload_to=EntityIdPath("chat_records/screenshots"), verbose_name="截图")
    ordering = models.PositiveIntegerField(default=0, verbose_name="顺序")
    title = models.CharField(max_length=255, blank=True, verbose_name="标题")
    note = models.TextField(blank=True, verbose_name="备注")
    capture_time_seconds = models.FloatField(null=True, blank=True, verbose_name="截图时间点(秒)")
    sha256 = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="内容哈希")
    dhash = models.CharField(max_length=16, blank=True, db_index=True, verbose_name="感知哈希")
    frame_score = models.FloatField(null=True, blank=True, verbose_name="帧评分")
    source = models.CharField(
        max_length=16, choices=ScreenshotSource.choices, default=ScreenshotSource.UNKNOWN, verbose_name="来源"
    )
    is_filtered = models.BooleanField(default=False, verbose_name="已过滤")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "聊天记录截图"
        verbose_name_plural = "聊天记录截图"
        ordering: ClassVar = ["ordering", "created_at"]
        indexes: ClassVar = [
            models.Index(fields=["project", "ordering"]),
            models.Index(fields=["project", "dhash"]),
            models.Index(fields=["project", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}-{self.id}"

    @hook(BEFORE_UPDATE, when="image", has_changed=True)
    def on_image_changed_delete_old(self) -> None:
        """image 字段变更时删除旧文件"""
        from apps.chat_records.signals import _delete_field_file_by_name

        _delete_field_file_by_name(self.initial_value("image"))
