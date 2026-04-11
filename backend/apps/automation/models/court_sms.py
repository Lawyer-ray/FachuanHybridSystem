"""法院短信相关模型"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from apps.automation.models.court_document import DocumentQueryHistory


class CourtSMSStatus(models.TextChoices):
    """短信处理状态"""

    PENDING = "pending", _("待处理")
    PARSING = "parsing", _("解析中")
    DOWNLOADING = "downloading", _("下载中")
    DOWNLOAD_FAILED = "download_failed", _("下载失败")
    MATCHING = "matching", _("匹配中")
    PENDING_MANUAL = "pending_manual", _("待人工处理")
    RENAMING = "renaming", _("重命名中")
    NOTIFYING = "notifying", _("通知中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("处理失败")


class CourtSMSType(models.TextChoices):
    """短信类型"""

    DOCUMENT_DELIVERY = "document_delivery", _("文书送达")
    INFO_NOTIFICATION = "info_notification", _("信息通知")
    FILING_NOTIFICATION = "filing_notification", _("立案通知")


class CourtSMS(models.Model):
    """法院短信记录"""

    id: int
    if TYPE_CHECKING:
        query_histories: RelatedManager[DocumentQueryHistory]
    # 原始内容
    content = models.TextField(verbose_name=_("短信内容"))
    received_at = models.DateTimeField(verbose_name=_("收到时间"))

    # 解析结果
    sms_type = models.CharField(
        max_length=32, choices=CourtSMSType.choices, null=True, blank=True, verbose_name=_("短信类型")
    )
    download_links = models.JSONField(default=list, verbose_name=_("下载链接列表"))
    case_numbers = models.JSONField(default=list, verbose_name=_("案号列表"))
    party_names = models.JSONField(default=list, verbose_name=_("当事人名称列表"))
    document_file_paths = models.JSONField(default=list, verbose_name=_("文书文件路径列表"))

    # 处理状态
    status = models.CharField(
        max_length=32, choices=CourtSMSStatus.choices, default=CourtSMSStatus.PENDING, verbose_name=_("处理状态")
    )
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    retry_count = models.IntegerField(default=0, verbose_name=_("重试次数"))

    # 关联
    scraper_task = models.ForeignKey(
        "automation.ScraperTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("下载任务"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("关联案件"),
    )
    case_log = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("案件日志"),
    )

    # 飞书通知
    feishu_sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("飞书发送时间"))
    feishu_error = models.TextField(null=True, blank=True, verbose_name=_("飞书发送错误"))

    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "automation"
        verbose_name = _("法院短信")
        verbose_name_plural = _("法院短信")
        ordering: ClassVar = ["-received_at"]
        indexes: ClassVar = [
            models.Index(fields=["status", "-received_at"]),
            models.Index(fields=["sms_type"]),
            models.Index(fields=["case"]),
        ]

    def __str__(self) -> str:
        return "短信 #{} - {} - {}".format(self.id, self.get_sms_type_display() or "未分类", self.get_status_display())
