"""法院文书相关模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class DocumentDownloadStatus(models.TextChoices):
    """文书下载状态"""

    PENDING = "pending", "待下载"
    DOWNLOADING = "downloading", "下载中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class CourtDocument(models.Model):
    """法院文书记录"""

    id: int
    # 关联字段
    scraper_task = models.ForeignKey(
        "automation.ScraperTask", on_delete=models.CASCADE, related_name="documents", verbose_name="爬虫任务"
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_documents",
        verbose_name="关联案件",
    )

    # API返回的原始字段
    c_sdbh = models.CharField(max_length=128, verbose_name="送达编号")
    c_stbh = models.CharField(max_length=512, verbose_name="上传编号")
    wjlj = models.URLField(max_length=1024, verbose_name="文件链接")
    c_wsbh = models.CharField(max_length=128, verbose_name="文书编号")
    c_wsmc = models.CharField(max_length=512, verbose_name="文书名称")
    c_fybh = models.CharField(max_length=64, verbose_name="法院编号")
    c_fymc = models.CharField(max_length=256, verbose_name="法院名称")
    c_wjgs = models.CharField(max_length=32, verbose_name="文件格式")
    dt_cjsj = models.DateTimeField(verbose_name="创建时间(原始)")

    # 下载状态字段
    download_status = models.CharField(
        max_length=32,
        choices=DocumentDownloadStatus.choices,
        default=DocumentDownloadStatus.PENDING,
        verbose_name="下载状态",
    )
    local_file_path = models.CharField(max_length=1024, null=True, blank=True, verbose_name="本地文件路径")
    file_size = models.BigIntegerField(null=True, blank=True, verbose_name="文件大小(字节)")
    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")

    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    downloaded_at = models.DateTimeField(null=True, blank=True, verbose_name="下载完成时间")

    class Meta:
        app_label = "automation"
        verbose_name = "法院文书"
        verbose_name_plural = "法院文书"
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
