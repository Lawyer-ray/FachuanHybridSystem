"""案例下载任务模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class CaseDownloadStatus(models.TextChoices):
    PENDING = "pending", "待执行"
    QUEUED = "queued", "排队中"
    RUNNING = "running", "执行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class CaseDownloadFormat(models.TextChoices):
    PDF = "pdf", "PDF"
    DOC = "doc", "Word"


class CaseDownloadTask(models.Model):
    """案例下载任务"""

    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="case_download_tasks",
        verbose_name="创建人",
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        related_name="case_download_tasks",
        verbose_name="站点账号",
    )

    case_numbers = models.TextField(verbose_name="案号列表")
    file_format = models.CharField(
        max_length=8,
        choices=CaseDownloadFormat.choices,
        default=CaseDownloadFormat.PDF,
        verbose_name="文件格式",
    )
    status = models.CharField(
        max_length=16,
        choices=CaseDownloadStatus.choices,
        default=CaseDownloadStatus.PENDING,
        verbose_name="状态",
    )
    total_count = models.PositiveIntegerField(default=0, verbose_name="总案例数")
    success_count = models.PositiveIntegerField(default=0, verbose_name="成功数")
    failed_count = models.PositiveIntegerField(default=0, verbose_name="失败数")

    message = models.CharField(max_length=255, blank=True, verbose_name="状态说明")
    error = models.TextField(blank=True, verbose_name="错误信息")

    q_task_id = models.CharField(max_length=64, blank=True, verbose_name="DjangoQ任务ID")

    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "案例下载任务"
        verbose_name_plural = "案例下载任务"
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.id} | {self.file_format} | {self.status}"


class CaseDownloadResult(models.Model):
    """案例下载结果"""

    task = models.ForeignKey(
        CaseDownloadTask,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="所属任务",
    )
    case_number = models.CharField(max_length=255, verbose_name="案号")
    title = models.CharField(max_length=500, blank=True, verbose_name="案例标题")
    court = models.CharField(max_length=255, blank=True, verbose_name="法院")
    judgment_date = models.CharField(max_length=32, blank=True, verbose_name="裁判日期")

    file_path = models.CharField(max_length=1024, verbose_name="文件路径")
    file_size = models.PositiveIntegerField(default=0, verbose_name="文件大小")
    file_format = models.CharField(
        max_length=8,
        choices=CaseDownloadFormat.choices,
        default=CaseDownloadFormat.PDF,
        verbose_name="文件格式",
    )

    status = models.CharField(max_length=16, default="success", verbose_name="状态")
    error_message = models.TextField(blank=True, verbose_name="错误信息")

    downloaded_at = models.DateTimeField(auto_now_add=True, verbose_name="下载时间")

    class Meta:
        verbose_name = "案例下载结果"
        verbose_name_plural = "案例下载结果"
        indexes: ClassVar = [
            models.Index(fields=["task", "case_number"]),
        ]

    def __str__(self) -> str:
        return ""
