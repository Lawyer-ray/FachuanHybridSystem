"""国家企业信用信息公示系统报告下载任务模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class GsxtReportStatus(models.TextChoices):
    """任务状态。"""

    PENDING = "pending", _("等待中")
    WAITING_CAPTCHA = "waiting_captcha", _("等待验证码")
    WAITING_EMAIL = "waiting_email", _("等待邮件")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class GsxtReportTask(models.Model):
    """国家企业信用信息公示系统报告下载任务。"""

    id: int

    client = models.ForeignKey(
        "client.Client",
        on_delete=models.CASCADE,
        related_name="gsxt_report_tasks",
        verbose_name=_("当事人"),
    )
    company_name = models.CharField(max_length=255, verbose_name=_("企业名称"))
    status = models.CharField(
        max_length=32,
        choices=GsxtReportStatus.choices,
        default=GsxtReportStatus.PENDING,
        verbose_name=_("状态"),
    )
    error_message = models.TextField(blank=True, verbose_name=_("错误信息"))
    report_file = models.FileField(
        upload_to="gsxt_reports/",
        null=True,
        blank=True,
        verbose_name=_("报告文件"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("企业信用报告任务")
        verbose_name_plural = _("企业信用报告任务")
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return ""
