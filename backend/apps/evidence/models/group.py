"""证据分组模型（争议焦点关联）"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceGroup(models.Model):
    """证据分组，对应案件的争议焦点"""

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="evidence_groups",
        verbose_name=_("案件"),
    )
    name = models.CharField(max_length=200, verbose_name=_("分组名称"))
    description = models.TextField(blank=True, verbose_name=_("说明"))
    sort_order = models.IntegerField(default=0, verbose_name=_("排序"))
    items = models.ManyToManyField(
        "documents.EvidenceItem",
        blank=True,
        related_name="groups",
        verbose_name=_("关联证据"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        app_label = "evidence"
        ordering: ClassVar = ["sort_order", "created_at"]
        verbose_name = _("证据分组")
        verbose_name_plural = _("证据分组")
        indexes: ClassVar = [
            models.Index(fields=["case", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name
