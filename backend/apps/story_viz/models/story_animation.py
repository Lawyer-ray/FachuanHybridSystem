from __future__ import annotations

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StoryVizType(models.TextChoices):
    TIMELINE = "timeline", _("时间线")
    RELATIONSHIP = "relationship", _("人物关系图")
    CLAIM_JUDGMENT = "claim_judgment", _("诉求 vs 判决")


class StoryAnimationStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("处理中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class StoryAnimationStage(models.TextChoices):
    QUEUED = "queued", _("已入队")
    EXTRACTING_FACTS = "extracting_facts", _("提取事实")
    DIRECTING_SCRIPT = "directing_script", _("编排脚本")
    RENDERING_LAYOUT = "rendering_layout", _("渲染布局")
    GENERATING_FRAGMENTS = "generating_fragments", _("生成视觉片段")
    COMPOSING_HTML = "composing_html", _("组装HTML")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class StoryAnimation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_title = models.CharField(max_length=255, verbose_name=_("文书标题"))
    source_text = models.TextField(verbose_name=_("文书原文"))
    viz_type = models.CharField(
        max_length=32,
        choices=StoryVizType.choices,
        default=StoryVizType.TIMELINE,
        verbose_name=_("可视化类型"),
    )
    status = models.CharField(
        max_length=32,
        choices=StoryAnimationStatus.choices,
        default=StoryAnimationStatus.PENDING,
        verbose_name=_("状态"),
    )
    current_stage = models.CharField(
        max_length=48,
        choices=StoryAnimationStage.choices,
        default=StoryAnimationStage.QUEUED,
        verbose_name=_("当前阶段"),
    )
    progress_percent = models.PositiveSmallIntegerField(default=0, verbose_name=_("进度"))
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name=_("任务ID"))
    cancel_requested = models.BooleanField(default=False, verbose_name=_("请求取消"))
    llm_model = models.CharField(max_length=128, blank=True, default="", verbose_name=_("LLM 模型"))
    source_hash = models.CharField(max_length=64, blank=True, default="", verbose_name=_("原文哈希"))
    facts_payload = models.JSONField(default=dict, blank=True, verbose_name=_("事实结构化结果"))
    script_payload = models.JSONField(default=dict, blank=True, verbose_name=_("动画脚本结果"))
    render_payload = models.JSONField(default=dict, blank=True, verbose_name=_("渲染骨架结果"))
    animation_html = models.TextField(blank=True, default="", verbose_name=_("动画HTML"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="story_animations",
        verbose_name=_("创建人"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("故事可视化")
        verbose_name_plural = _("故事可视化")
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["viz_type", "-created_at"]),
            models.Index(fields=["source_hash"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_title} ({self.get_status_display()})"
