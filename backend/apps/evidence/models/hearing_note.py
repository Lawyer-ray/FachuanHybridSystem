"""庭审笔记模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class HearingNote(models.Model):
    """庭审笔记，可关联证据项"""

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="hearing_notes",
        verbose_name=_("案件"),
    )
    content = models.TextField(verbose_name=_("笔记内容"))
    evidence_items = models.ManyToManyField(
        "documents.EvidenceItem",
        blank=True,
        related_name="hearing_notes",
        verbose_name=_("关联证据"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("记录时间"))

    class Meta:
        app_label = "evidence"
        ordering: ClassVar = ["-created_at"]
        verbose_name = _("庭审笔记")
        verbose_name_plural = _("庭审笔记")
        indexes: ClassVar = [
            models.Index(fields=["case", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} - {self.content[:30]}"
