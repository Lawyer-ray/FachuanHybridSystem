from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.filesystem.upload_paths import DatedUUIDPath

from .article import ReviewStatus

_audio_upload_path = DatedUUIDPath("content_ops/audio")


class PodcastEpisode(models.Model):
    article = models.ForeignKey(
        "content_ops.GeneratedArticle",
        on_delete=models.CASCADE,
        related_name="episodes",
        verbose_name=_("文章"),
    )
    task = models.ForeignKey(
        "content_ops.ContentTask",
        on_delete=models.CASCADE,
        related_name="episodes",
        verbose_name=_("任务"),
    )
    voice = models.CharField(max_length=32, verbose_name=_("TTS音色"))
    audio_file = models.FileField(
        upload_to=_audio_upload_path,
        max_length=255,
        blank=True,
        verbose_name=_("音频文件"),
    )
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("时长(秒)")
    )
    file_size_bytes = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("文件大小(字节)")
    )

    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus,
        default="draft",
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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("播客单集")
        verbose_name_plural = _("播客单集")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.article.title} ({self.voice})"
