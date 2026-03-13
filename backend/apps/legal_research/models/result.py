from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext_lazy as _


def _result_pdf_upload_to(instance: Any, filename: str) -> str:
    return f"legal_research/{instance.task_id}/{instance.id}/{filename}"


class LegalResearchResult(models.Model):
    legacy_uuid = models.UUIDField(default=uuid4, editable=False, db_index=True, verbose_name=_("历史UUID"))
    task = models.ForeignKey(
        "legal_research.LegalResearchTask",
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("任务"),
    )

    rank = models.PositiveIntegerField(default=0, verbose_name=_("命中顺序"))
    source_doc_id = models.CharField(max_length=255, verbose_name=_("源文档ID"))
    source_url = models.TextField(blank=True, verbose_name=_("源链接"))

    title = models.CharField(max_length=512, blank=True, verbose_name=_("标题"))
    court_text = models.CharField(max_length=255, blank=True, verbose_name=_("法院"))
    document_number = models.CharField(max_length=255, blank=True, verbose_name=_("案号"))
    judgment_date = models.CharField(max_length=64, blank=True, verbose_name=_("裁判日期"))
    case_digest = models.TextField(blank=True, verbose_name=_("摘要"))

    similarity_score = models.FloatField(default=0.0, verbose_name=_("相似度分数"))
    match_reason = models.TextField(blank=True, verbose_name=_("匹配理由"))

    pdf_file = models.FileField(
        upload_to=_result_pdf_upload_to,
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("PDF文件"),
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("扩展信息"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("案例检索结果")
        verbose_name_plural = _("案例检索结果")
        ordering: ClassVar = ["rank", "created_at"]
        indexes: ClassVar = [
            models.Index(fields=["task", "rank"]),
            models.Index(fields=["task", "source_doc_id"]),
        ]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["task", "source_doc_id"], name="uniq_legal_research_task_source_doc"),
        ]

    def __str__(self) -> str:
        return f"{self.task_id} | {self.rank} | {self.title[:32]}"
