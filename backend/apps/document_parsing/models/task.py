"""文档解析任务 Model（存储解析结果）"""

import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class DocumentParsingTask(models.Model):
    """文档解析任务

    存储每次文档解析的结果，包括纯文本、Markdown 和元数据。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    file_name = models.CharField("文件名", max_length=255)
    file_path = models.CharField("文件路径", max_length=500)
    file_size = models.PositiveIntegerField("文件大小（字节）", default=0)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    backend_used = models.CharField("解析后端", max_length=50, blank=True)
    text = models.TextField("纯文本", blank=True)
    markdown = models.TextField("Markdown", blank=True)
    metadata = models.JSONField("元数据", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "解析任务"
        verbose_name_plural = "解析任务"

    def __str__(self) -> str:
        return f"#{self.id} {self.file_name} ({self.get_status_display()})"

    @property
    def metadata_pprint(self) -> str:
        """格式化的元数据（用于 Admin 展示）"""
        import json

        if not self.metadata:
            return "{}"
        try:
            return json.dumps(self.metadata, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(self.metadata)

    def mark_processing(self) -> None:
        """标记为处理中"""
        self.status = self.Status.PROCESSING
        self.save(update_fields=["status"])

    def mark_completed(self, text: str, markdown: str, metadata: dict, backend_used: str) -> None:
        """标记为完成"""
        self.status = self.Status.COMPLETED
        self.text = text
        self.markdown = markdown
        self.metadata = metadata
        self.backend_used = backend_used
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "text", "markdown", "metadata", "backend_used", "completed_at"])

    def mark_failed(self, error_message: str) -> None:
        """标记为失败"""
        self.status = self.Status.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])
