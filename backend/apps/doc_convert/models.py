"""doc_convert 模型：虚拟入口 + 要素式转换历史记录。"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.filesystem.upload_paths import DatedUUIDPath, MediaEntity


class DocConvertTool(models.Model):
    """虚拟模型，不创建数据库表，仅作为 Admin 入口。"""

    class Meta:
        managed = False
        app_label = "doc_convert"
        verbose_name = "要素式转换"
        verbose_name_plural = "要素式转换"


class DocConvertRecord(models.Model):
    """要素式转换历史记录。

    convert 端点原先是纯转发（转换完直接把 docx 二进制吐给前端、不落库），
    关掉弹窗产物即失。此表把每次转换的产物存档，供历史弹窗重新下载。
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    original_name = models.CharField("原文件名", max_length=255)
    mbid = models.CharField("文书类型标识", max_length=64, db_index=True)
    mbid_name = models.CharField("文书类型名", max_length=128, blank=True, default="")
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.SUCCESS)
    error_message = models.TextField("错误信息", blank=True, default="")
    output_file = models.FileField(
        "转换产物",
        upload_to=DatedUUIDPath(MediaEntity.DOC_CONVERT_OUTPUT),
        blank=True,
        default="",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doc_convert_records",
        verbose_name="发起人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        app_label = "doc_convert"
        ordering = ["-created_at"]
        verbose_name = "要素式转换记录"
        verbose_name_plural = "要素式转换记录"
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"#{self.id} {self.original_name} ({self.get_status_display()})"
