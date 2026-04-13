"""Module for evidence chunk."""

from datetime import datetime
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceChunk(models.Model):
    evidence_item_id: int  # Django 自动生成的外键 ID 字段
    evidence_item: models.ForeignKey[models.Model, models.Model] = models.ForeignKey(
        "documents.EvidenceItem",
        on_delete=models.CASCADE,
        related_name="ai_chunks",
    )
    page_start: int | None = models.IntegerField(null=True, blank=True)  # type: ignore[assignment]
    page_end: int | None = models.IntegerField(null=True, blank=True)  # type: ignore[assignment]
    text: str = models.TextField(blank=True, default="")  # type: ignore[assignment]
    embedding: list[Any] = models.JSONField(default=list, blank=True)  # type: ignore[assignment]
    extraction_method: str = models.CharField(max_length=20, blank=True, default="")  # type: ignore[assignment]
    created_at: datetime = models.DateTimeField(auto_now_add=True)  # type: ignore[assignment]
    updated_at: datetime = models.DateTimeField(auto_now=True)  # type: ignore[assignment]

    class Meta:
        app_label = "litigation_ai"
        verbose_name = _("证据片段")
        verbose_name_plural = _("证据片段")
        indexes: ClassVar = [
            models.Index(fields=["evidence_item"]),
        ]
