"""Business logic services."""

from __future__ import annotations

from apps.core.dto import EvidenceItemDigestDTO
from apps.documents.models import EvidenceItem

_VALUES = ("id", "order", "name", "purpose", "page_start", "page_end", "file")


class EvidenceQueryService:
    def _build_dtos(self, items: list[dict]) -> list[EvidenceItemDigestDTO]:
        file_field = EvidenceItem._meta.get_field("file")
        results: list[EvidenceItemDigestDTO] = []
        for item in items:
            file_path = None
            if item.get("file"):
                try:
                    file_path = file_field.storage.path(item["file"])
                except Exception:
                    # 静默处理:文件操作失败不影响主流程
                    file_path = None
            results.append(
                EvidenceItemDigestDTO(
                    id=item["id"],
                    order=item.get("order") or 0,
                    name=item.get("name") or "",
                    purpose=item.get("purpose") or "",
                    page_start=item.get("page_start"),
                    page_end=item.get("page_end"),
                    file_path=file_path,
                )
            )
        return results

    def list_evidence_items_for_digest_internal(
        self,
        evidence_list_ids: list[int],
        evidence_item_ids: list[int],
    ) -> list[EvidenceItemDigestDTO]:
        qs = EvidenceItem.objects.all()
        if evidence_item_ids:
            qs = qs.filter(id__in=evidence_item_ids)
        elif evidence_list_ids:
            qs = qs.filter(evidence_list_id__in=evidence_list_ids)
        else:
            return []
        return self._build_dtos(list(qs.order_by("evidence_list_id", "order").values(*_VALUES)))

    def list_evidence_item_ids_with_files_internal(self, evidence_item_ids: list[int]) -> list[EvidenceItemDigestDTO]:
        if not evidence_item_ids:
            return []
        items = list(EvidenceItem.objects.filter(id__in=evidence_item_ids, file__isnull=False).values(*_VALUES))
        return self._build_dtos(items)

    def list_evidence_items_for_case_internal(self, case_id: int) -> list[EvidenceItemDigestDTO]:
        items = list(
            EvidenceItem.objects.filter(evidence_list__case_id=case_id)
            .order_by("evidence_list_id", "order")
            .values(*_VALUES)
        )
        return self._build_dtos(items)
