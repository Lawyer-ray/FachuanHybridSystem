"""Business logic services."""

from __future__ import annotations

from apps.core.error_catalog import evidence_item_not_found, evidence_list_not_found
from apps.documents.models import EvidenceItem, EvidenceList


class EvidenceBasicQueryService:
    def get_evidence_list(self, list_id: int) -> EvidenceList:
        try:
            return EvidenceList.objects.get(id=list_id)
        except EvidenceList.DoesNotExist:
            raise evidence_list_not_found(list_id=list_id) from None

    def list_evidence_lists(self, case_id: int) -> list[EvidenceList]:
        return list(
            EvidenceList.objects.filter(case_id=case_id).prefetch_related("items").order_by("order", "created_at")
        )

    def get_evidence_item(self, item_id: int) -> EvidenceItem:
        try:
            return EvidenceItem.objects.get(id=item_id)
        except EvidenceItem.DoesNotExist:
            raise evidence_item_not_found(item_id=item_id) from None

    def list_items_for_list(self, list_id: int) -> list[EvidenceItem]:
        return list(EvidenceItem.objects.filter(evidence_list_id=list_id).order_by("order"))
