from __future__ import annotations

from typing import ClassVar

from django.db import models

class EvidenceType(models.TextChoices):
    WRITTEN_CONTRACT = "written_contract", "书面合同"
    DELIVERY_RECEIPT = "delivery_receipt", "送货/收货凭证"
    RECONCILIATION = "reconciliation", "对账确认"
    COLLECTION_RECORD = "collection_record", "催款记录"
    PAYMENT_RECORD = "payment_record", "付款记录"

class EvidenceScore(models.Model):
    id: int
    assessment_id: int
    assessment: models.ForeignKey[models.Model, models.Model] = models.ForeignKey(
        "sales_dispute.CaseAssessment",
        on_delete=models.CASCADE,
        related_name="evidence_scores",
        verbose_name="关联评估记录",
    )
    evidence_type: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=EvidenceType.choices,
        verbose_name="证据类型",
    )
    has_evidence: bool = models.BooleanField(default=False, verbose_name="是否具备")  # type: ignore[assignment]
    quality_score: int = models.IntegerField(default=0, verbose_name="证据质量评分")  # type: ignore[assignment]
    remarks: str = models.TextField(blank=True, default="", verbose_name="备注")  # type: ignore[assignment]

    class Meta:
        verbose_name = "证据评分明细"
        verbose_name_plural = "证据评分明细"
        unique_together: ClassVar = [("assessment", "evidence_type")]

    def __str__(self) -> str:
        evidence_labels = {
            EvidenceType.WRITTEN_CONTRACT.value: "书面合同",
            EvidenceType.DELIVERY_RECEIPT.value: "送货/收货凭证",
            EvidenceType.RECONCILIATION.value: "对账确认",
            EvidenceType.COLLECTION_RECORD.value: "催款记录",
            EvidenceType.PAYMENT_RECORD.value: "付款记录",
        }
        label = evidence_labels.get(self.evidence_type, self.evidence_type)
        return f"{label}: {self.quality_score}"
