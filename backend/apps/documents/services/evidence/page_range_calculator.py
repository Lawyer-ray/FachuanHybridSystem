"""Business logic services."""

from __future__ import annotations

from django.db import transaction

from apps.documents.models import EvidenceList


class EvidencePageRangeCalculator:
    def calculate_page_ranges(self, *, evidence_list: EvidenceList) -> None:
        items = evidence_list.items.filter(file__isnull=False).order_by("order")

        current_page = evidence_list.start_page
        total_pages = 0

        for item in items:
            if item.page_count > 0:
                item.page_start = current_page
                item.page_end = current_page + item.page_count - 1
                current_page = item.page_end + 1
                total_pages += item.page_count
                item.save(update_fields=["page_start", "page_end"])

        evidence_list.total_pages = total_pages
        evidence_list.save(update_fields=["total_pages", "updated_at"])

    @transaction.atomic
    def recalculate_page_ranges_for_chain(self, *, list_id: int) -> None:
        evidence_list = EvidenceList.objects.get(id=list_id)

        self.calculate_page_ranges(evidence_list=evidence_list)

        next_lists = EvidenceList.objects.filter(
            case_id=evidence_list.case_id,
            order__gt=evidence_list.order,
        ).order_by("order")
        for next_list in next_lists:
            self.calculate_page_ranges(evidence_list=next_list)

    def update_subsequent_lists_pages(self, *, case_id: int, start_order: int) -> None:
        next_lists = EvidenceList.objects.filter(case_id=case_id, order__gte=start_order).order_by("order")
        for evidence_list in next_lists:
            self.calculate_page_ranges(evidence_list=evidence_list)
