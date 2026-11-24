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
    name = models.CharField(max_length=64, default="Document Recognition")

    class Meta:
        managed = False
        verbose_name = "文书智能识别"
        verbose_name_plural = "文书智能识别"


class DocumentRecognitionTask(models.Model):
    """文书识别任务。"""

    id: int
    file_path = models.CharField(max_length=1024, verbose_name="文件路径")
    original_filename = models.CharField(max_length=256, verbose_name="原始文件名")
    status = models.CharField(
        max_length=32,
        choices=DocumentRecognitionStatus.choices,
        default=DocumentRecognitionStatus.PENDING,
        verbose_name="任务状态",
    )
    document_type = models.CharField(max_length=32, blank=True, default="", verbose_name="文书类型")
    case_number = models.CharField(max_length=128, blank=True, default="", verbose_name="案号")
    key_time = models.DateTimeField(null=True, blank=True, verbose_name="关键时间")
    confidence = models.FloatField(null=True, blank=True, verbose_name="置信度")
    extraction_method = models.CharField(max_length=32, blank=True, default="", verbose_name="提取方式")
    llm_model = models.CharField(max_length=100, blank=True, default="", verbose_name="LLM 模型")
    llm_backend = models.CharField(max_length=32, blank=True, default="", verbose_name="LLM 后端")
    llm_latency_ms = models.IntegerField(null=True, blank=True, verbose_name="LLM 耗时(ms)")
    degraded = models.BooleanField(null=True, blank=True, verbose_name="降级识别")
    raw_text = models.TextField(blank=True, default="", verbose_name="原始文本")
    party_names = models.JSONField(default=list, blank=True, verbose_name="识别出的当事人")
    renamed_file_path = models.CharField(max_length=1024, blank=True, default="", verbose_name="重命名后路径")
    binding_success = models.BooleanField(null=True, verbose_name="绑定成功")
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
    binding_message = models.CharField(max_length=512, blank=True, default="", verbose_name="绑定消息")
    binding_error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="绑定错误码")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    notification_sent = models.BooleanField(default=False, verbose_name="通知已发送")
    notification_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="通知发送时间")
    notification_error = models.TextField(blank=True, default="", verbose_name="通知错误信息")
    notification_file_sent = models.BooleanField(default=False, verbose_name="文件已发送")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    date_confirmation_status = models.CharField(
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
    source_document_path = models.CharField(max_length=1024, blank=True, default="", verbose_name="来源文书路径")
    """来源管线送识别的原文件绝对路径（幂等键：同一短信的同一份文书只建一次任务）。

    法院短信场景下 file_path 与它相同；独立上传场景为空串。单靠 file_path 不能做幂等：
    重跑（retry）复用同一行，而"重新送识别"走的是新建行。
    """
    classification_hint = models.CharField(max_length=32, blank=True, default="", verbose_name="文书类型提示")
    """来源管线给出的文书类型提示（仅在分类器认不出时兜底，非空即表示用了兜底）。"""
    suppressed_candidates = models.JSONField(default=list, blank=True, verbose_name="被过滤的日期候选")
    """被日期闸门过滤掉的候选项（留痕，供「为什么没提醒我」追问）。

    法院送达的 8~12 份文书里，大部分是通用告知/须知类，正文里的「N 日内」讲的不是
    本案期限（如「申请不予公布的，至迟应在裁判文书送达之日起三日内」）。这类候选
    现在会被直接丢弃，但**丢弃也要留一行**——律师问「这份文书为什么没生成提醒」时
    必须答得出，且后续调参需要回放。每项形如
    ``{due_at, reminder_type, reason, context_text, anchor_document}``。
    """
    created_by: Any = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_recognition_tasks",
        verbose_name="创建人",
    )

    class Meta:
        managed = True
        db_table = "automation_documentrecognitiontask"
        verbose_name = "文书识别任务"
        verbose_name_plural = "文书识别任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        # 该表带 raw_text 持续增长，按 status 过滤（工作台待确认列表）依赖复合索引；
        # case/case_log 为 FK，建表时（automation/0005 create_model）已自带单列索引
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"], name="idx_docrec_status_created"),
            # 法院短信自动送识别的幂等查询：按 (来源短信, 来源文书路径) 定位存量任务
            models.Index(fields=["source_court_sms", "source_document_path"], name="idx_docrec_sms_source_path"),
        ]

    def __str__(self) -> str:
        return f"识别任务 #{self.id} - {self.get_status_display()}"


class DocumentRecognitionDateCandidate(models.Model):
    """文书识别出的关键日期候选（律师逐条人工确认后才写入重要日期提醒）。

    **为什么有出处字段（2026-11-24 事故复盘）**：历史上候选只存
    ``(due_at, reminder_type, context_text, source, confidence)``，表达不了
    「这个期限依据哪份文书、起算锚是什么、现在到底能不能算」。结果是所有语义判断
    都塌缩成 ``confidence`` 一个数字：通用须知里「收到《缴费通知书》之日起七日内」
    被按「收到本短信 + 7 天」算出一个日期，还打了 0.85、默认勾选。
    现在一条候选必须能回答「谁对谁、何时、依据哪份文书、锚点是什么」，
    判据与口径见 ``date_candidate_policy`` 与
    ``docs/analysis/date-candidate-provenance-2026-11-24/SUMMARY.md``。
    """

    id: int
    task: Any = models.ForeignKey(
        DocumentRecognitionTask,
        on_delete=models.CASCADE,
        related_name="date_candidates",
        verbose_name="识别任务",
    )
    due_at = models.DateTimeField(verbose_name="候选日期时间")
    reminder_type = models.CharField(
        max_length=64,
        choices=ReminderType.choices,
        default="other",
        verbose_name="提醒类型",
    )
    context_text = models.CharField(max_length=255, default="", blank=True, verbose_name="原文上下文")
    source = models.CharField(
        max_length=16,
        default="regex",
        verbose_name="提取来源",
    )
    confidence = models.FloatField(null=True, blank=True, verbose_name="置信度")
    status = models.CharField(
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
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    # —— 出处（provenance）：一条候选凭什么可信 ——
    anchor_kind = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="起算锚类型",
        help_text="service_of_self=本份文书送达日；issue_date_of_self=文书落款日；"
        "effective_date=判决生效日；foreign_document=锚点在别的文书；unknown=无法判断",
    )
    anchor_at = models.DateField(null=True, blank=True, verbose_name="起算锚日期")
    """锚点自身的日期（送达日/落款日）。与 due_at 一起才能复算「锚 + N 天」。"""
    anchor_document = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="锚点文书归属",
        help_text="self=本文书；other_in_batch=同批另一份文书；future_document=尚未产生的文书；other_case=他案文书",
    )
    derivation = models.CharField(
        max_length=24,
        blank=True,
        default="",
        verbose_name="推算方式",
        help_text="llm_absolute=LLM 读到的明文日期；rule_absolute=正则读到的明文日期；"
        "rule_period=期间结构推算；rule_relative=相对期限（锚 + N 天）推算",
    )
    review_flags = models.JSONField(default=list, blank=True, verbose_name="复核标记")
    """空列表 = 可以默认勾选。非空必须人工看：anchor_effective / generic_boilerplate /
    low_confidence / far_future / duplicate / discarded_by_gate。"""
    default_checked = models.BooleanField(default=False, verbose_name="默认勾选")
    """后端算好的默认勾选策略（= review_flags 为空且未被丢弃）。前端不再按裸分数判断。"""
    duplicate_of: Any = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
        verbose_name="权威候选",
    )
    """批内去重：指向同一条短信里更权威的那条候选（本行随之 skipped）。"""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "日期候选"
        verbose_name_plural = "日期候选"
        ordering: ClassVar[list[str]] = ["due_at", "id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["task", "status"])]

    def __str__(self) -> str:
        return f"日期候选 #{self.id} {self.due_at:%Y-%m-%d %H:%M} ({self.get_status_display()})"
