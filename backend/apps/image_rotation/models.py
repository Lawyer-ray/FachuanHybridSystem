"""Models for image rotation tools."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ImageRotationTool(models.Model):
    """Admin entry model for image rotation."""

    id: int
    name: str = models.CharField(max_length=64, default="Image Rotation")  # type: ignore[assignment]

    class Meta:
        managed = False
        verbose_name = _("图片自动旋转")
        verbose_name_plural = _("图片自动旋转")
