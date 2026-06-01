from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ReviewStatus(models.TextChoices):
    DRAFT = "draft", _("待审核")
    APPROVED = "approved", _("已通过")
    REJECTED = "rejected", _("已驳回")


class GeneratedArticle(models.Model):
    task = models.ForeignKey(
        "content_ops.ContentTask",
        on_delete=models.CASCADE,
        related_name="articles",
        verbose_name=_("任务"),
    )
    title = models.CharField(max_length=200, verbose_name=_("文章标题"))
    content = models.TextField(verbose_name=_("正文"))
    source_summary = models.TextField(blank=True, verbose_name=_("原始内容摘要"))

    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus,
        default=ReviewStatus.DRAFT,
        verbose_name=_("审核状态"),
    )
    reviewer_notes = models.TextField(blank=True, verbose_name=_("审核备注"))
    reviewed_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("审核人"),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("审核时间"))

    llm_model = models.CharField(max_length=128, blank=True, verbose_name=_("使用的模型"))
    token_usage = models.JSONField(default=dict, blank=True, verbose_name=_("Token用量"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("生成文章")
        verbose_name_plural = _("生成文章")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
