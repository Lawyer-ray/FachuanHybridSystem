"""爬虫任务相关模型"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from apps.automation.models.court_document import CourtDocument
    from apps.automation.models.court_sms import CourtSMS


class ScraperTaskType(models.TextChoices):
    """爬虫任务类型"""

    COURT_DOCUMENT = "court_document", _("下载司法文书")
    COURT_FILING = "court_filing", _("自动立案")
    JUSTICE_BUREAU = "justice_bureau", _("司法局操作")
    POLICE = "police", _("公安局操作")


class ScraperTaskStatus(models.TextChoices):
    """爬虫任务状态"""

    PENDING = "pending", _("等待中")
    RUNNING = "running", _("执行中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class ScraperTask(models.Model):
    """网络爬虫任务"""

    id: int
    if TYPE_CHECKING:
        documents: RelatedManager[CourtDocument]
        court_sms_records: RelatedManager[CourtSMS]
    task_type = models.CharField(max_length=32, choices=ScraperTaskType.choices, verbose_name=_("任务类型"))
    status = models.CharField(
        max_length=32, choices=ScraperTaskStatus.choices, default=ScraperTaskStatus.PENDING, verbose_name=_("状态")
    )
    priority = models.IntegerField(default=5, verbose_name=_("优先级"), help_text=_("1-10,数字越小优先级越高"))
    url = models.URLField(verbose_name=_("目标URL"))
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scraper_tasks",
        verbose_name=_("关联案件"),
    )
    config = models.JSONField(default=dict, verbose_name=_("配置"), help_text=_("存储账号、密码、文件路径等"))
    result = models.JSONField(null=True, blank=True, verbose_name=_("执行结果"))
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    retry_count = models.IntegerField(default=0, verbose_name=_("重试次数"))
    max_retries = models.IntegerField(default=3, verbose_name=_("最大重试次数"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    scheduled_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("计划执行时间"), help_text=_("留空则立即执行")
    )

    class Meta:
        app_label: str = "automation"
        verbose_name = _("任务管理")
        verbose_name_plural = _("任务管理")
        ordering: ClassVar = ["priority", "-created_at"]  # 优先级优先,然后按创建时间
        indexes: ClassVar = [
            models.Index(fields=["status", "priority", "-created_at"]),
            models.Index(fields=["task_type"]),
            models.Index(fields=["case"]),
            models.Index(fields=["scheduled_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_task_type_display()} - {self.get_status_display()}"

    def can_retry(self) -> bool:
        """判断是否可以重试"""
        return self.retry_count < self.max_retries

    def should_execute_now(self) -> bool:
        """判断是否应该立即执行"""
        from django.utils import timezone

        if self.scheduled_at is None:
            return True
        return self.scheduled_at <= timezone.now()
