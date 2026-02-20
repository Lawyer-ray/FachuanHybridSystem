"""Module for evidence chunk."""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceChunk(models.Model):
    evidence_item = models.ForeignKey(
        "documents.EvidenceItem",
        on_delete=models.CASCADE,
        related_name="ai_chunks",
    )
    evidence_item_id: int  # Django 自动生成的外键 ID 字段
    page_start = models.IntegerField(null=True, blank=True)
    page_end = models.IntegerField(null=True, blank=True)
    text = models.TextField(blank=True, default="")
    embedding = models.JSONField(default=list, blank=True)
    extraction_method = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "litigation_ai"
        verbose_name = _("证据片段")
        verbose_name_plural = _("证据片段")
        indexes: ClassVar = [
            models.Index(fields=["evidence_item"]),
        ]
