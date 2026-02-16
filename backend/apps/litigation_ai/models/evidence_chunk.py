"""Module for evidence chunk."""

from typing import ClassVar

from django.db import models


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
        app_label: str = "litigation_ai"
        indexes: ClassVar = [
            models.Index(fields=["evidence_item"]),
        ]
