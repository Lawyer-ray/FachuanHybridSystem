from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.filesystem.upload_paths import DatedUUIDPath


class DocConverterJobStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    CONVERTING = "converting", _("转换中")
    PACKING = "packing", _("打包中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class DocConverterTool(models.Model):
    """虚拟模型，仅用于 Admin 侧边栏入口"""

    name = models.CharField(max_length=64, default="Doc Converter")

    class Meta:
        managed = False
        verbose_name = _("DOC 转 DOCX")
        verbose_name_plural = _("DOC 转 DOCX")


class DocConverterJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=20,
        choices=DocConverterJobStatus.choices,
        default=DocConverterJobStatus.PENDING,
        verbose_name=_("状态"),
    )
    total_files = models.PositiveIntegerField(_("总文件数"), default=0)
    converted_files = models.PositiveIntegerField(_("已转换数"), default=0)
    failed_files = models.PositiveIntegerField(_("失败数"), default=0)
    progress = models.PositiveIntegerField(_("进度(0-100)"), default=0)
    cancel_requested = models.BooleanField(_("请求取消"), default=False)
    task_id = models.CharField(_("Django Q2 任务ID"), max_length=255, blank=True, default="")
    output_zip = models.FileField(_("结果ZIP"), upload_to=DatedUUIDPath("doc_converter_zip"), blank=True, default="")
    error_message = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doc_converter_jobs",
        verbose_name=_("创建人"),
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        db_table = "doc_converter_job"
        verbose_name = _("DOC 转换任务")
        verbose_name_plural = _("DOC 转换任务")
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"DOC转换任务 {self.id} ({self.get_status_display()})"


class DocConverterItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(DocConverterJob, on_delete=models.CASCADE, related_name="items", verbose_name=_("任务"))
    original_name = models.CharField(_("原始文件名"), max_length=500)
    source_file = models.FileField(_("源文件"), upload_to=DatedUUIDPath("doc_converter_source"))
    converted_file = models.FileField(
        _("转换后文件"), upload_to=DatedUUIDPath("doc_converter_output"), blank=True, default=""
    )
    status = models.CharField(
        max_length=20,
        choices=DocConverterJobStatus.choices,
        default=DocConverterJobStatus.PENDING,
        verbose_name=_("状态"),
    )
    error = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    duration_ms = models.FloatField(null=True, blank=True, verbose_name=_("耗时(ms)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        db_table = "doc_converter_item"
        verbose_name = _("DOC 转换项")
        verbose_name_plural = _("DOC 转换项")
        ordering: ClassVar[list[str]] = ["created_at"]

    def __str__(self) -> str:
        return self.original_name
