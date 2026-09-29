"""Models for document recognition."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, ClassVar

from django.db import models

from apps.reminders.models import ReminderType


class DocumentRecognitionStatus(models.TextChoices):
    """文书识别任务状态。"""

    PENDING = "pending", "待处理"
    PROCESSING = "processing", "识别中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class DateCandidateStatus(models.TextChoices):
    """日期候选确认状态（行级状态机）。"""

    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已确认"
    SKIPPED = "skipped", "已忽略"


class DateConfirmationStatus(models.TextChoices):
    """任务级日期确认进度（冗余字段，供 admin 筛选与工作台侧栏）。"""

    NONE = "none", "无日期候选"
    PENDING = "pending", "待确认"
    PARTIAL = "partial", "部分确认"
    COMPLETE = "complete", "全部处理完"


class DocumentRecognitionTool(models.Model):
    """Admin entry model for document recognition."""

    id: int
    name: str = models.CharField(max_length=64, default="Document Recognition")

    class Meta:
        managed = False
        verbose_name = "文书智能识别"
        verbose_name_plural = "文书智能识别"


class DocumentRecognitionTask(models.Model):
    """文书识别任务。"""

    id: int
    file_path: str = models.CharField(max_length=1024, verbose_name="文件路径")
    original_filename: str = models.CharField(max_length=256, verbose_name="原始文件名")
    status: str = models.CharField(
        max_length=32,
        choices=DocumentRecognitionStatus.choices,
        default=DocumentRecognitionStatus.PENDING,
        verbose_name="任务状态",
    )
    document_type: str | None = models.CharField(max_length=32, null=True, blank=True, verbose_name="文书类型")
    case_number: str | None = models.CharField(max_length=128, null=True, blank=True, verbose_name="案号")
    key_time: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name="关键时间")
    confidence: float | None = models.FloatField(null=True, blank=True, verbose_name="置信度")
    extraction_method: str | None = models.CharField(max_length=32, null=True, blank=True, verbose_name="提取方式")
    llm_model: str | None = models.CharField(max_length=100, null=True, blank=True, verbose_name="LLM 模型")
    llm_backend: str | None = models.CharField(max_length=32, null=True, blank=True, verbose_name="LLM 后端")
    llm_latency_ms: int | None = models.IntegerField(null=True, blank=True, verbose_name="LLM 耗时(ms)")
    degraded: bool | None = models.BooleanField(null=True, blank=True, verbose_name="降级识别")
    raw_text: str | None = models.TextField(null=True, blank=True, verbose_name="原始文本")
    party_names: Any = models.JSONField(default=list, blank=True, verbose_name="识别出的当事人")
    renamed_file_path: str | None = models.CharField(
        max_length=1024, null=True, blank=True, verbose_name="重命名后路径"
    )
    binding_success: bool | None = models.BooleanField(null=True, verbose_name="绑定成功")
    case: Any = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name="关联案件",
    )
    case_log: Any = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name="案件日志",
    )
    binding_message: str | None = models.CharField(max_length=512, null=True, blank=True, verbose_name="绑定消息")
    binding_error_code: str | None = models.CharField(max_length=64, null=True, blank=True, verbose_name="绑定错误码")
    error_message: str | None = models.TextField(null=True, blank=True, verbose_name="错误信息")
    notification_sent: bool = models.BooleanField(default=False, verbose_name="通知已发送")
    notification_sent_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name="通知发送时间")
    notification_error: str | None = models.TextField(null=True, blank=True, verbose_name="通知错误信息")
    notification_file_sent: bool = models.BooleanField(default=False, verbose_name="文件已发送")
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    date_confirmation_status: str = models.CharField(
        max_length=16,
        choices=DateConfirmationStatus.choices,
        default=DateConfirmationStatus.NONE,
        db_index=True,
        verbose_name="日期确认状态",
    )
    source_court_sms: Any = models.ForeignKey(
        "automation.CourtSMS",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="recognition_tasks",
        verbose_name="来源法院短信",
    )

    class Meta:
        managed = True
        db_table = "automation_documentrecognitiontask"
        verbose_name = "文书识别任务"
        verbose_name_plural = "文书识别任务"
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"识别任务 #{self.id} - {self.get_status_display()}"


class DocumentRecognitionDateCandidate(models.Model):
    """文书识别出的关键日期候选（律师逐条人工确认后才写入重要日期提醒）。"""

    id: int
    task: Any = models.ForeignKey(
        DocumentRecognitionTask,
        on_delete=models.CASCADE,
        related_name="date_candidates",
        verbose_name="识别任务",
    )
    due_at: datetime = models.DateTimeField(verbose_name="候选日期时间")
    reminder_type: str = models.CharField(
        max_length=64,
        choices=ReminderType.choices,
        default="other",
        verbose_name="提醒类型",
    )
    context_text: str = models.CharField(max_length=255, default="", blank=True, verbose_name="原文上下文")
    source: str = models.CharField(
        max_length=16,
        default="regex",
        verbose_name="提取来源",
    )
    confidence: float | None = models.FloatField(null=True, blank=True, verbose_name="置信度")
    status: str = models.CharField(
        max_length=16,
        choices=DateCandidateStatus.choices,
        default=DateCandidateStatus.PENDING,
        db_index=True,
        verbose_name="确认状态",
    )
    reminder: Any = models.ForeignKey(
        "reminders.Reminder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_candidates",
        verbose_name="已写入的提醒",
    )
    confirmed_by: Any = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_date_candidates",
        verbose_name="确认人",
    )
    confirmed_at: datetime | None = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    created_at: datetime = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at: datetime = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "日期候选"
        verbose_name_plural = "日期候选"
        ordering: ClassVar[list[str]] = ["due_at", "id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["task", "status"])]

    def __str__(self) -> str:
        return f"日期候选 #{self.id} {self.due_at:%Y-%m-%d %H:%M} ({self.get_status_display()})"
