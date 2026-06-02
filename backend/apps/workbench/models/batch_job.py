"""批量任务模型

通用的批量任务抽象，当前用于案例文档批量分析，未来可扩展到其他批量任务。
遵循 PdfSplitJob 的模式：Job + Item 双层结构，协作式取消，节流式进度更新。
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.filesystem.upload_paths import DatedUUIDPath


class BatchJobStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    RUNNING = "running", "运行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class BatchJob(models.Model):
    """通用批量任务"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "workbench.WorkbenchSession",
        on_delete=models.CASCADE,
        related_name="batch_jobs",
        verbose_name="关联会话",
    )
    job_type = models.CharField(
        "任务类型",
        max_length=50,
        default="doc_analysis",
        help_text="doc_analysis, 未来可扩展其他类型",
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=BatchJobStatus.choices,
        default=BatchJobStatus.PENDING,
    )
    prompt = models.TextField("分析要求")
    llm_model = models.CharField("LLM 模型", max_length=255, blank=True, default="")
    total_items = models.PositiveIntegerField("总文件数", default=0)
    completed_items = models.PositiveIntegerField("已完成数", default=0)
    failed_items = models.PositiveIntegerField("失败数", default=0)
    progress = models.PositiveIntegerField("进度", default=0, help_text="0-100")
    cancel_requested = models.BooleanField("请求取消", default=False)
    task_id = models.CharField("Django Q2 任务ID", max_length=255, blank=True, default="")
    summary = models.TextField("汇总结论", blank=True, default="")
    summary_file = models.FileField("汇总文件", upload_to=DatedUUIDPath("workbench_summary"), blank=True, default="")
    detail_zip_file = models.FileField(
        "分析详情 ZIP", upload_to=DatedUUIDPath("workbench_detail"), blank=True, default=""
    )
    metadata = models.JSONField("元数据", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    started_processing_at = models.DateTimeField("首个文件开始处理时间", null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "workbench_batch_job"
        verbose_name = "批量任务"
        verbose_name_plural = "批量任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"BatchJob {self.id} ({self.get_status_display()})"


class BatchJobItem(models.Model):
    """批量任务的单个子项"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        BatchJob,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="所属任务",
    )
    file_name = models.CharField("文件名", max_length=500)
    file = models.FileField("文件", upload_to=DatedUUIDPath("workbench_batch"))
    status = models.CharField(
        "状态",
        max_length=20,
        choices=BatchJobStatus.choices,
        default=BatchJobStatus.PENDING,
    )
    result = models.TextField("分析结论", blank=True, default="")
    error = models.TextField("错误信息", blank=True, default="")
    duration_ms = models.FloatField("耗时(ms)", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "workbench_batch_job_item"
        verbose_name = "批量任务子项"
        verbose_name_plural = "批量任务子项"
        ordering: ClassVar[list[str]] = ["created_at"]

    def __str__(self) -> str:
        return f"{self.file_name} ({self.get_status_display()})"


@receiver(post_delete, sender=BatchJobItem)
def delete_item_file(sender: type, instance: BatchJobItem, **kwargs: object) -> None:
    """删除子项时清理上传的文件"""
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=BatchJob)
def delete_job_summary_file(sender: type, instance: BatchJob, **kwargs: object) -> None:
    """删除任务时清理汇总文件"""
    if instance.summary_file:
        instance.summary_file.delete(save=False)
    if instance.detail_zip_file:
        instance.detail_zip_file.delete(save=False)
