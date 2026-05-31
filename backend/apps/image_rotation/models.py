"""Models for image rotation tools."""

from __future__ import annotations

from django.db import models

class ImageRotationTool(models.Model):
    """Admin entry model for image rotation."""

    id: int
    name: str = models.CharField(max_length=64, default="Image Rotation")  # type: ignore[assignment]

    class Meta:
        managed = False
        verbose_name = "图片自动旋转"
        verbose_name_plural = "图片自动旋转"
