"""Models for fee notice tools."""

from __future__ import annotations

from django.db import models

class FeeNoticeTool(models.Model):
    """Admin entry model for fee notice recognition."""

    id: int
    name: str = models.CharField(max_length=64, default="Fee Notice")  # type: ignore[assignment]

    class Meta:
        managed = False
        verbose_name = "交费通知书识别"
        verbose_name_plural = "交费通知书识别"
