"""庭审笔记模型"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

class HearingNote(models.Model):
    """庭审笔记，可关联证据项"""

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="hearing_notes",
        verbose_name="案件",
    )
    content = models.TextField(verbose_name="笔记内容")
    evidence_items = models.ManyToManyField(
        "documents.EvidenceItem",
        blank=True,
        related_name="hearing_notes",
        verbose_name="关联证据",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")

    class Meta:
        app_label = "evidence"
        ordering: ClassVar = ["-created_at"]
        verbose_name = "庭审笔记"
        verbose_name_plural = "庭审笔记"
        indexes: ClassVar = [
            models.Index(fields=["case", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} - {self.content[:30]}"
