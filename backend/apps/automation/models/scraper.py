"""爬虫任务相关模型"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django_lifecycle import AFTER_UPDATE, LifecycleModel, hook

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from apps.automation.models.court_document import CourtDocument
    from apps.automation.models.court_sms import CourtSMS

logger = logging.getLogger("apps.automation")


class ScraperTaskType(models.TextChoices):
    """爬虫任务类型"""

    COURT_DOCUMENT = "court_document", "下载司法文书"
    COURT_FILING = "court_filing", "自动立案"
    JUSTICE_BUREAU = "justice_bureau", "司法局操作"
    POLICE = "police", "公安局操作"


class ScraperTaskStatus(models.TextChoices):
    """爬虫任务状态"""

    PENDING = "pending", "等待中"
    RUNNING = "running", "执行中"
    WAITING_FOR_CAPTCHA = "waiting_for_captcha", "等待验证码"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ScraperTask(LifecycleModel):
    """网络爬虫任务"""

    id: int
    if TYPE_CHECKING:
        documents: RelatedManager[CourtDocument]
        court_sms_records: RelatedManager[CourtSMS]
    task_type = models.CharField(max_length=32, choices=ScraperTaskType.choices, verbose_name="任务类型")
    status = models.CharField(
        max_length=32, choices=ScraperTaskStatus.choices, default=ScraperTaskStatus.PENDING, verbose_name="状态"
    )
    priority = models.IntegerField(default=5, verbose_name="优先级", help_text="1-10,数字越小优先级越高")
    url = models.URLField(verbose_name="目标URL")
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scraper_tasks",
        verbose_name="关联案件",
    )
    config = models.JSONField(default=dict, verbose_name="配置", help_text="存储账号、密码、文件路径等")
    result = models.JSONField(null=True, blank=True, verbose_name="执行结果")
    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")
    retry_count = models.IntegerField(default=0, verbose_name="重试次数")
    max_retries = models.IntegerField(default=3, verbose_name="最大重试次数")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name="计划执行时间", help_text="留空则立即执行")
    captcha_image_path = models.CharField(
        max_length=500, null=True, blank=True, verbose_name="验证码图片路径", help_text="手动验证码模式下存储待识别图片路径"
    )
    captcha_answer = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="验证码答案", help_text="用户手动输入的验证码答案"
    )

    class Meta:
        app_label = "automation"
        verbose_name = "任务管理"
        verbose_name_plural = "任务管理"
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

    @hook(AFTER_UPDATE, when="status", has_changed=True)
    def on_status_change_trigger_sms_flow(self) -> None:
        """状态变为 SUCCESS/FAILED 时委托 Service 层处理 CourtSMS 后续流程

        使用 submit_task 将实际的 ORM 查询和后续处理提交到 Django-Q worker，
        避免在 model save 事务内执行大量 ORM I/O 阻塞保存操作。
        """
        if self.status not in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
            return

        try:
            from apps.core.tasking import submit_task

            task_id = submit_task(
                "apps.automation.workers.court_sms_tasks.handle_scraper_task_status_change",
                self.id,
                task_name=f"scraper_sms_flow_{self.id}",
            )
            logger.info(
                "提交 ScraperTask 状态变更后续处理: Task ID=%s, Queue Task ID=%s",
                self.id,
                task_id,
            )
        except Exception as e:
            logger.error(
                "❌ 提交下载完成信号处理任务失败: Task ID=%s, 错误: %s",
                self.id,
                e,
                extra={"action": "download_signal_submit_failed", "task_id": self.id, "error": str(e)},
                exc_info=True,
            )
