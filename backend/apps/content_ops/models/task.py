from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ContentTaskMode(models.TextChoices):
    SEARCH = "search", _("检索模式")
    DIRECT = "direct", _("直投模式")


class ContentTaskStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    QUEUED = "queued", _("队列中")
    RUNNING = "running", _("执行中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class ContentTaskOutputMode(models.TextChoices):
    NARRATION = "narration", _("单人叙事")
    DISCUSSION = "discussion", _("多人讨论")
    BOTH = "both", _("两者都要")


class ContentTask(models.Model):
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_ops_tasks",
        verbose_name=_("创建人"),
    )
    mode = models.CharField(
        max_length=16,
        choices=ContentTaskMode,
        default=ContentTaskMode.SEARCH,
        verbose_name=_("模式"),
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="content_ops_tasks",
        verbose_name=_("法律检索网站账号"),
    )
    keyword = models.CharField(max_length=255, blank=True, verbose_name=_("检索关键词"))
    case_summary = models.TextField(blank=True, verbose_name=_("案情简述"))
    direct_content = models.TextField(blank=True, verbose_name=_("直投内容"))

    # Source document info (populated after search or from direct content)
    source_doc_id = models.CharField(max_length=255, blank=True, verbose_name=_("威科文档ID"))
    source_title = models.CharField(max_length=512, blank=True, verbose_name=_("文书标题"))
    source_court_text = models.CharField(max_length=255, blank=True, verbose_name=_("法院"))
    source_judgment_date = models.CharField(max_length=64, blank=True, verbose_name=_("裁判日期"))
    source_facts = models.TextField(blank=True, verbose_name=_("案件事实"))

    voice = models.CharField(max_length=32, default="冰糖", verbose_name=_("TTS音色"))
    tts_style_prompt = models.TextField(
        blank=True,
        default="",
        verbose_name=_("VoiceDesign 音色描述"),
        help_text=_("自然语言描述期望的声音风格，使用 VoiceDesign 模式合成。留空则使用内置音色。"),
    )

    output_mode = models.CharField(
        max_length=16,
        choices=ContentTaskOutputMode,
        default=ContentTaskOutputMode.NARRATION,
        verbose_name=_("输出模式"),
    )
    discussion_speakers = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("讨论角色配置"),
        help_text=_("多人讨论模式的角色列表，格式: [{name, role, style_prompt}]"),
    )

    # Task lifecycle
    status = models.CharField(
        max_length=16,
        choices=ContentTaskStatus,
        default=ContentTaskStatus.PENDING,
        verbose_name=_("状态"),
    )
    progress = models.PositiveIntegerField(default=0, verbose_name=_("进度"))
    message = models.CharField(max_length=255, blank=True, verbose_name=_("状态描述"))
    error = models.TextField(blank=True, verbose_name=_("错误信息"))
    q_task_id = models.CharField(max_length=64, blank=True, verbose_name=_("队列任务ID"))

    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("内容运营任务")
        verbose_name_plural = _("内容运营任务")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["mode", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_mode_display()}] {self.keyword or self.source_title or self.pk}"
