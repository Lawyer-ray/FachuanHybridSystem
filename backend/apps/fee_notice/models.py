"""Models for fee notice tools."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class FeeNoticeTool(models.Model):
    """Admin entry model for fee notice recognition."""

    id: int
    name = models.CharField(max_length=64, default="Fee Notice")

    class Meta:
        managed = False
        verbose_name = _("交费通知书识别")
        verbose_name_plural = _("交费通知书识别")
