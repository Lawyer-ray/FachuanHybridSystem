"""Models for preservation date tools."""

from __future__ import annotations

from django.db import models

class PreservationDateTool(models.Model):
    """Admin entry model for preservation date extraction."""

    id: int
    name: str = models.CharField(max_length=64, default="Preservation Date")  # type: ignore[assignment]

    class Meta:
        managed = False
        verbose_name = "财产保全日期识别"
        verbose_name_plural = "财产保全日期识别"
