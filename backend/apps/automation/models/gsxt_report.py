"""国家企业信用信息公示系统报告下载任务模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.core.filesystem.upload_paths import DatedUUIDPath, MediaEntity


class GsxtReportStatus(models.TextChoices):
    """任务状态。"""

    PENDING = "pending", "等待中"
    WAITING_CAPTCHA = "waiting_captcha", "等待验证码"
    WAITING_EMAIL = "waiting_email", "等待邮件"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class GsxtReportTask(models.Model):
    """国家企业信用信息公示系统报告下载任务。"""

    id: int

    client = models.ForeignKey(
        "client.Client",
        on_delete=models.CASCADE,
        related_name="gsxt_report_tasks",
        verbose_name="当事人",
    )
    company_name = models.CharField(max_length=255, verbose_name="企业名称")
    credit_code = models.CharField(max_length=64, blank=True, verbose_name="统一社会信用代码")
    status = models.CharField(
        max_length=32,
        choices=GsxtReportStatus.choices,
        default=GsxtReportStatus.PENDING,
        verbose_name="状态",
    )
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    report_file = models.FileField(
        upload_to=DatedUUIDPath(MediaEntity.GSXT_REPORTS),
        null=True,
        blank=True,
        verbose_name="报告文件",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        app_label = "automation"
        verbose_name = "企业信用报告任务"
        verbose_name_plural = "企业信用报告任务"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return ""
