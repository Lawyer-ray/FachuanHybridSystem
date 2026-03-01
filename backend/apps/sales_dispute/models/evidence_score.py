from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceType(models.TextChoices):
    WRITTEN_CONTRACT = "written_contract", _("书面合同")
    DELIVERY_RECEIPT = "delivery_receipt", _("送货/收货凭证")
    RECONCILIATION = "reconciliation", _("对账确认")
    COLLECTION_RECORD = "collection_record", _("催款记录")
    PAYMENT_RECORD = "payment_record", _("付款记录")


class EvidenceScore(models.Model):
    id: int
    assessment = models.ForeignKey(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="evidence_scores",
        verbose_name=_("关联评估记录"),
    )
    evidence_type = models.CharField(
        max_length=32,
        choices=EvidenceType.choices,
        verbose_name=_("证据类型"),
    )
    has_evidence = models.BooleanField(default=False, verbose_name=_("是否具备"))
    quality_score = models.IntegerField(default=0, verbose_name=_("证据质量评分"))
    remarks = models.TextField(blank=True, default="", verbose_name=_("备注"))

    class Meta:
        verbose_name = _("证据评分明细")
        verbose_name_plural = _("证据评分明细")
        unique_together: ClassVar = [("assessment", "evidence_type")]

    def __str__(self) -> str:
        return f"{self.get_evidence_type_display()}: {self.quality_score}"
