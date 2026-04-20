"""爬虫任务相关模型"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_lifecycle import AFTER_UPDATE, LifecycleModel, hook

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from apps.automation.models.court_document import CourtDocument
    from apps.automation.models.court_sms import CourtSMS

logger = logging.getLogger("apps.automation")


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


class ScraperTask(LifecycleModel):
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
        app_label = "automation"
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

    @hook(AFTER_UPDATE, when="status", has_changed=True)
    def on_status_change_trigger_sms_flow(self) -> None:
        """状态变为 SUCCESS/FAILED 时触发 CourtSMS 后续处理流程"""
        if self.status not in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
            return

        try:
            from apps.automation.models.court_sms import CourtSMS, CourtSMSStatus
            from apps.core.tasking import ScheduleQueryService, submit_task

            court_sms_records = CourtSMS.objects.filter(scraper_task=self)
            for sms in court_sms_records:
                if sms.status not in [CourtSMSStatus.DOWNLOADING, CourtSMSStatus.MATCHING]:
                    continue
                if self.status == ScraperTaskStatus.SUCCESS:
                    self._handle_sms_download_success(sms)
                elif self.status == ScraperTaskStatus.FAILED:
                    if self._handle_sms_download_failed(sms):
                        continue
        except Exception as e:
            logger.error(
                "❌ 处理下载完成信号失败: Task ID=%s, 错误: %s",
                self.id,
                e,
                extra={"action": "download_signal_failed", "task_id": self.id, "error": str(e)},
                exc_info=True,
            )

    def _handle_sms_download_success(self, sms: "CourtSMS") -> None:
        """处理下载成功的 SMS"""
        from apps.automation.models.court_sms import CourtSMSStatus
        from apps.core.tasking import submit_task

        if sms.status == CourtSMSStatus.DOWNLOADING:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
            logger.info("✅ 下载任务完成，进入匹配阶段: SMS ID=%s, Task ID=%s", sms.id, self.id)
        elif sms.status == CourtSMSStatus.MATCHING:
            logger.info("✅ 下载任务完成，继续匹配流程: SMS ID=%s, Task ID=%s", sms.id, self.id)

        task_id = submit_task(
            "apps.automation.services.sms.court_sms_service.process_sms_async",
            sms.id,
            task_name=f"court_sms_continue_{sms.id}",
        )
        logger.info("提交后续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)

    def _handle_sms_download_failed(self, sms: "CourtSMS") -> bool:
        """处理下载失败的 SMS，返回是否需要 continue（跳过重试逻辑）"""
        from apps.automation.models.court_sms import CourtSMSStatus
        from apps.core.tasking import ScheduleQueryService, submit_task

        if sms.status == CourtSMSStatus.MATCHING:
            logger.info("下载失败但继续匹配流程: SMS ID=%s", sms.id)
            task_id = submit_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_continue_after_download_failed_{sms.id}",
            )
            logger.info("下载失败后继续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)
            return True

        sms.status = CourtSMSStatus.DOWNLOAD_FAILED
        sms.error_message = self.error_message or "下载任务失败"
        sms.save()
        logger.warning(
            "⚠️ 下载任务失败: SMS ID=%s, Task ID=%s, 错误: %s",
            sms.id,
            self.id,
            self.error_message,
        )

        if sms.retry_count < 3:
            from datetime import timedelta

            from django.utils import timezone

            next_run = timezone.now() + timedelta(seconds=60)
            ScheduleQueryService().create_once_schedule(
                func="apps.automation.services.sms.court_sms_service.retry_download_task",
                args=str(sms.id),
                name=f"court_sms_retry_download_{sms.id}",
                next_run=next_run,
            )
            logger.info("提交重试下载任务: SMS ID=%s, 计划执行时间=%s", sms.id, next_run)
        else:
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"下载失败，已重试{sms.retry_count}次"
            sms.save()
            logger.error("下载重试次数用完，标记为失败: SMS ID=%s", sms.id)
        return False
