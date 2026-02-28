"""案件材料整理虚拟模型"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceSorting(models.Model):
    """案件材料整理工具虚拟模型"""

    id: int
    name = models.CharField(max_length=64, default="Evidence Sorting")

    class Meta:
        managed = False
        verbose_name = _("案件材料整理")
        verbose_name_plural = _("案件材料整理")
