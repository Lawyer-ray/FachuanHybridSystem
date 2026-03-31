"""doc_convert 虚拟模型，仅用于挂载 Django Admin 入口。"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocConvertTool(models.Model):
    """虚拟模型，不创建数据库表，仅作为 Admin 入口。"""

    class Meta:
        managed = False
        app_label = "doc_convert"
        verbose_name = _("传统文书转换")
        verbose_name_plural = _("传统文书转换")
