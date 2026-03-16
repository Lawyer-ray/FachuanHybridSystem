"""Models for preservation date tools."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class PreservationDateTool(models.Model):
    """Admin entry model for preservation date extraction."""

    id: int
    name = models.CharField(max_length=64, default="Preservation Date")

    class Meta:
        managed = False
        verbose_name = _("财产保全日期识别")
        verbose_name_plural = _("财产保全日期识别")
