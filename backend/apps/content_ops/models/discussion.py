from __future__ import annotations

from django.db import models

from .article import ReviewStatus

class DiscussionScript(models.Model):
    """多人讨论脚本。"""

    task = models.ForeignKey(
        "content_ops.ContentTask",
        on_delete=models.CASCADE,
        related_name="discussion_scripts",
        verbose_name="任务",
    )
    title = models.CharField(max_length=200, verbose_name="标题")
    topic = models.TextField(blank=True, verbose_name="讨论主题")
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus,
        default=ReviewStatus.DRAFT,
        verbose_name="审核状态",
    )
    reviewer_notes = models.TextField(blank=True, verbose_name="审核备注")
    reviewed_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="审核人",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="审核时间")
    llm_model = models.CharField(max_length=128, blank=True, verbose_name="LLM模型")
    token_usage = models.JSONField(default=dict, blank=True, verbose_name="Token用量")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "讨论脚本"
        verbose_name_plural = "讨论脚本"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

class DiscussionTurn(models.Model):
    """讨论脚本中的单轮对话。"""

    script = models.ForeignKey(
        DiscussionScript,
        on_delete=models.CASCADE,
        related_name="turns",
        verbose_name="脚本",
    )
    speaker_name = models.CharField(max_length=64, verbose_name="说话人")
    speaker_style_prompt = models.TextField(blank=True, verbose_name="VoiceDesign 音色描述")
    text = models.TextField(verbose_name="对话内容")
    order = models.PositiveIntegerField(default=0, verbose_name="顺序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "对话轮次"
        verbose_name_plural = "对话轮次"
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.speaker_name}: {self.text[:30]}"
