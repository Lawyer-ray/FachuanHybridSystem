from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class BatchPrintJobStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("处理中")
    COMPLETED = "completed", _("已完成")
    PARTIAL_FAILED = "partial_failed", _("部分失败")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class BatchPrintItemStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("处理中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class BatchPrintFileType(models.TextChoices):
    PDF = "pdf", _("PDF")
    DOCX = "docx", _("DOCX")


class BatchPrintingTool(models.Model):
    id: int
    name: str = models.CharField(max_length=64, default="Batch Printing")

    class Meta:
        managed = False
        verbose_name = _("批量打印")
        verbose_name_plural = _("批量打印")


class PrintPresetSnapshot(models.Model):
    printer_name: str = models.CharField(max_length=255, verbose_name=_("打印机名称"))
    printer_display_name: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("打印机展示名称"))
    preset_name: str = models.CharField(max_length=255, verbose_name=_("预置名称"))
    preset_source: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("预置来源"))
    raw_settings_payload: Any = models.JSONField(default=dict, blank=True, verbose_name=_("原始设置"))
    executable_options_payload: Any = models.JSONField(default=dict, blank=True, verbose_name=_("可执行打印参数"))
    supported_option_names: Any = models.JSONField(default=list, blank=True, verbose_name=_("驱动支持参数名"))
    last_synced_at: datetime = models.DateTimeField(verbose_name=_("最近同步时间"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("打印预置快照")
        verbose_name_plural = _("打印预置快照")
        ordering: ClassVar[list[str]] = ["printer_name", "preset_name", "-updated_at"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["printer_name", "preset_name"], name="batch_printing_preset_unique"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["printer_name", "preset_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.printer_name} / {self.preset_name}"


class PrintKeywordRule(models.Model):
    keyword: str = models.CharField(max_length=255, verbose_name=_("关键词"))
    priority: int = models.PositiveIntegerField(default=100, verbose_name=_("优先级"))
    enabled: bool = models.BooleanField(default=True, verbose_name=_("启用"))
    printer_name: str = models.CharField(max_length=255, verbose_name=_("目标打印机"))
    preset_snapshot: Any = models.ForeignKey(
        PrintPresetSnapshot,
        on_delete=models.PROTECT,
        related_name="rules",
        verbose_name=_("目标预置"),
    )
    notes: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备注"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("关键词打印规则")
        verbose_name_plural = _("关键词打印规则")
        ordering: ClassVar[list[str]] = ["priority", "id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["enabled", "priority"]),
        ]

    def __str__(self) -> str:
        return f"{self.keyword} -> {self.printer_name}/{self.preset_snapshot.preset_name}"


class BatchPrintJob(models.Model):
    id: UUID = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status: str = models.CharField(
        max_length=32,
        choices=BatchPrintJobStatus.choices,
        default=BatchPrintJobStatus.PENDING,
        verbose_name=_("状态"),
    )
    total_count: int = models.PositiveIntegerField(default=0, verbose_name=_("总文件数"))
    processed_count: int = models.PositiveIntegerField(default=0, verbose_name=_("已处理数量"))
    success_count: int = models.PositiveIntegerField(default=0, verbose_name=_("成功数量"))
    failed_count: int = models.PositiveIntegerField(default=0, verbose_name=_("失败数量"))
    progress: int = models.PositiveIntegerField(default=0, verbose_name=_("进度"))
    task_id: str = models.CharField(max_length=64, blank=True, default="", verbose_name=_("任务ID"))
    cancel_requested: bool = models.BooleanField(default=False, verbose_name=_("请求取消"))
    created_by: Any = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_print_jobs",
        verbose_name=_("创建人"),
    )
    capability_payload: Any = models.JSONField(default=dict, blank=True, verbose_name=_("能力快照"))
    summary_payload: Any = models.JSONField(default=dict, blank=True, verbose_name=_("任务摘要"))
    error_message: str = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    started_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("批量打印任务")
        verbose_name_plural = _("批量打印任务")
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.get_status_display()})"


class BatchPrintItem(models.Model):
    job: Any = models.ForeignKey(
        BatchPrintJob,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("批次任务"),
    )
    order: int = models.PositiveIntegerField(default=1, verbose_name=_("排序"))
    source_original_name: str = models.CharField(max_length=255, verbose_name=_("原始文件名"))
    source_relpath: str = models.CharField(max_length=1024, verbose_name=_("源文件相对路径"))
    prepared_relpath: str = models.CharField(max_length=1024, blank=True, default="", verbose_name=_("打印文件相对路径"))
    file_type: str = models.CharField(max_length=16, choices=BatchPrintFileType.choices, verbose_name=_("文件类型"))
    matched_rule: Any = models.ForeignKey(
        PrintKeywordRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_items",
        verbose_name=_("命中规则"),
    )
    matched_keyword: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("命中关键词"))
    target_preset: Any = models.ForeignKey(
        PrintPresetSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_items",
        verbose_name=_("目标预置"),
    )
    target_printer_name: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("目标打印机"))
    target_preset_name: str = models.CharField(max_length=255, blank=True, default="", verbose_name=_("目标预置名称"))
    status: str = models.CharField(
        max_length=32,
        choices=BatchPrintItemStatus.choices,
        default=BatchPrintItemStatus.PENDING,
        verbose_name=_("状态"),
    )
    cups_job_id: str = models.CharField(max_length=64, blank=True, default="", verbose_name=_("CUPS 任务ID"))
    error_message: str = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    started_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("批量打印明细")
        verbose_name_plural = _("批量打印明细")
        ordering: ClassVar[list[str]] = ["order", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["job", "order"], name="batch_printing_item_job_order_unique"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["job", "status"]),
            models.Index(fields=["target_printer_name", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_original_name} ({self.get_status_display()})"


@receiver(post_delete, sender=BatchPrintJob)
def delete_job_files(sender: type, instance: BatchPrintJob, **kwargs: object) -> None:
    """删除任务时清理关联文件目录。"""
    from apps.batch_printing.services.storage import BatchPrintStorage

    BatchPrintStorage(instance.id).cleanup()
