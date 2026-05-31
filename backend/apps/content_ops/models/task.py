from __future__ import annotations

from django.db import models

class ContentTaskMode(models.TextChoices):
    SEARCH = "search", "检索模式"
    DIRECT = "direct", "直投模式"

class ContentTaskStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    QUEUED = "queued", "队列中"
    RUNNING = "running", "执行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class ContentTaskOutputMode(models.TextChoices):
    NARRATION = "narration", "单人叙事"
    DISCUSSION = "discussion", "多人讨论"
    BOTH = "both", "两者都要"

class ContentTask(models.Model):
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_ops_tasks",
        verbose_name="创建人",
    )
    mode = models.CharField(
        max_length=16,
        choices=ContentTaskMode,
        default=ContentTaskMode.SEARCH,
        verbose_name="模式",
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="content_ops_tasks",
        verbose_name="法律检索网站账号",
    )
    keyword = models.CharField(max_length=255, blank=True, verbose_name="检索关键词")
    case_summary = models.TextField(blank=True, verbose_name="案情简述")
    direct_content = models.TextField(blank=True, verbose_name="直投内容")

    # Source document info (populated after search or from direct content)
    source_doc_id = models.CharField(max_length=255, blank=True, verbose_name="威科文档ID")
    source_title = models.CharField(max_length=512, blank=True, verbose_name="文书标题")
    source_court_text = models.CharField(max_length=255, blank=True, verbose_name="法院")
    source_judgment_date = models.CharField(max_length=64, blank=True, verbose_name="裁判日期")
    source_facts = models.TextField(blank=True, verbose_name="案件事实")

    voice = models.CharField(max_length=32, default="冰糖", verbose_name="TTS音色")
    tts_style_prompt = models.TextField(
        blank=True,
        default="",
        verbose_name="VoiceDesign 音色描述",
        help_text="自然语言描述期望的声音风格，使用 VoiceDesign 模式合成。留空则使用内置音色。",
    )

    output_mode = models.CharField(
        max_length=16,
        choices=ContentTaskOutputMode,
        default=ContentTaskOutputMode.NARRATION,
        verbose_name="输出模式",
    )
    discussion_speakers = models.JSONField(
        default=list,
        blank=True,
        verbose_name="讨论角色配置",
        help_text="多人讨论模式的角色列表，格式: [{name, role, style_prompt}]",
    )

    # Task lifecycle
    status = models.CharField(
        max_length=16,
        choices=ContentTaskStatus,
        default=ContentTaskStatus.PENDING,
        verbose_name="状态",
    )
    progress = models.PositiveIntegerField(default=0, verbose_name="进度")
    message = models.CharField(max_length=255, blank=True, verbose_name="状态描述")
    error = models.TextField(blank=True, verbose_name="错误信息")
    q_task_id = models.CharField(max_length=64, blank=True, verbose_name="队列任务ID")

    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "内容运营任务"
        verbose_name_plural = "内容运营任务"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["mode", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_mode_display()}] {self.keyword or self.source_title or self.pk}"
