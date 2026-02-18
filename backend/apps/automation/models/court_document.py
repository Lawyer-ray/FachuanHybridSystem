"""法院文书相关模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentDownloadStatus(models.TextChoices):
    """文书下载状态"""

    PENDING = "pending", _("待下载")
    DOWNLOADING = "downloading", _("下载中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class CourtDocument(models.Model):
    """法院文书记录"""

    id: int
    # 关联字段
    scraper_task = models.ForeignKey(
        "automation.ScraperTask", on_delete=models.CASCADE, related_name="documents", verbose_name=_("爬虫任务")
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_documents",
        verbose_name=_("关联案件"),
    )

    # API返回的原始字段
    c_sdbh = models.CharField(max_length=128, verbose_name=_("送达编号"))
    c_stbh = models.CharField(max_length=512, verbose_name=_("上传编号"))
    wjlj = models.URLField(max_length=1024, verbose_name=_("文件链接"))
    c_wsbh = models.CharField(max_length=128, verbose_name=_("文书编号"))
    c_wsmc = models.CharField(max_length=512, verbose_name=_("文书名称"))
    c_fybh = models.CharField(max_length=64, verbose_name=_("法院编号"))
    c_fymc = models.CharField(max_length=256, verbose_name=_("法院名称"))
    c_wjgs = models.CharField(max_length=32, verbose_name=_("文件格式"))
    dt_cjsj = models.DateTimeField(verbose_name=_("创建时间(原始)"))

    # 下载状态字段
    download_status = models.CharField(
        max_length=32,
        choices=DocumentDownloadStatus.choices,
        default=DocumentDownloadStatus.PENDING,
        verbose_name=_("下载状态"),
    )
    local_file_path = models.CharField(max_length=1024, null=True, blank=True, verbose_name=_("本地文件路径"))
    file_size = models.BigIntegerField(null=True, blank=True, verbose_name=_("文件大小(字节)"))
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))

    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("记录创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))
    downloaded_at = models.DateTimeField(null=True, blank=True, verbose_name=_("下载完成时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("法院文书")
        verbose_name_plural = _("法院文书")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["scraper_task", "download_status"]),
            models.Index(fields=["case"]),
            models.Index(fields=["c_wsbh"]),
            models.Index(fields=["c_fymc"]),
            models.Index(fields=["download_status"]),
            models.Index(fields=["created_at"]),
        ]
        unique_together: ClassVar = [["c_wsbh", "c_sdbh"]]  # 文书编号+送达编号唯一

    def __str__(self) -> str:
        return f"{self.c_wsmc} - {self.get_download_status_display()}"

    @property
    def absolute_file_path(self) -> str:
        """获取文件的绝对路径"""
        if not self.local_file_path:
            return ""
        from pathlib import Path

        from django.conf import settings

        # 如果已经是绝对路径,直接返回
        file_path = Path(self.local_file_path)
        if file_path.is_absolute():
            return str(file_path)
        # 否则拼接 MEDIA_ROOT
        return str(Path(settings.MEDIA_ROOT) / self.local_file_path)


class DocumentQueryHistory(models.Model):
    """文书查询历史"""

    id: int
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="document_query_histories",
        verbose_name=_("账号凭证"),
    )
    case_number = models.CharField(max_length=128, verbose_name=_("案号"))
    send_time = models.DateTimeField(verbose_name=_("文书发送时间"))
    court_sms = models.ForeignKey(
        "automation.CourtSMS",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="query_histories",
        verbose_name=_("关联短信记录"),
    )
    queried_at = models.DateTimeField(auto_now_add=True, verbose_name=_("查询时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("文书查询历史")
        verbose_name_plural = _("文书查询历史")
        unique_together: ClassVar = [["credential", "case_number", "send_time"]]
        indexes: ClassVar = [
            models.Index(fields=["credential", "case_number"]),
            models.Index(fields=["send_time"]),
        ]

    def __str__(self) -> str:
        return "{} - {} - {}".format(self.credential, self.case_number, self.send_time.strftime("%Y-%m-%d %H:%M"))


class DocumentDeliverySchedule(models.Model):
    """文书送达定时任务"""

    id: int
    credential_id: int  # 外键ID字段
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="delivery_schedules",
        verbose_name=_("账号凭证"),
    )
    runs_per_day = models.PositiveIntegerField(default=1, verbose_name=_("每天运行次数"))
    hour_interval = models.PositiveIntegerField(
        default=24, verbose_name=_("运行间隔(小时)"), help_text=_("在24小时内的运行间隔")
    )
    cutoff_hours = models.PositiveIntegerField(
        default=24, verbose_name=_("截止时间(小时)"), help_text=_("只处理最近N小时内的文书")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name=_("上次运行时间"))
    next_run_at = models.DateTimeField(null=True, blank=True, verbose_name=_("下次运行时间"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "automation"
        verbose_name = _("文书送达定时任务")
        verbose_name_plural = _("文书送达定时任务")
        indexes: ClassVar = [
            models.Index(fields=["is_active", "next_run_at"]),
            models.Index(fields=["credential"]),
        ]

    def __str__(self) -> str:
        return "{} - 每天{}次 - {}".format(self.credential, self.runs_per_day, "启用" if self.is_active else "禁用")
