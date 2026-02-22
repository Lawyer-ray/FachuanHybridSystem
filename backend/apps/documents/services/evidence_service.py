"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.documents.models import EvidenceItem, EvidenceList

logger = logging.getLogger(__name__)
from apps.documents.services.evidence import (
    EvidenceFileService,
    EvidenceMutationService,
    EvidencePageRangeCalculator,
    EvidenceQueryService,
)

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService


class EvidenceService:
    SUPPORTED_FORMATS = EvidenceFileService.SUPPORTED_FORMATS
    MAX_FILE_SIZE = EvidenceFileService.MAX_FILE_SIZE

    def __init__(
        self,
        case_service: ICaseService | None = None,
        query_service: EvidenceQueryService | None = None,
        mutation_service: EvidenceMutationService | None = None,
        file_service: EvidenceFileService | None = None,
        page_range_calculator: EvidencePageRangeCalculator | None = None,
    ) -> None:
        self._case_service = case_service
        self._query_service = query_service or EvidenceQueryService()
        self._mutation_service = mutation_service or EvidenceMutationService()
        self._file_service = file_service or EvidenceFileService()
        self._page_range_calculator = page_range_calculator or EvidencePageRangeCalculator()

    @property
    def case_service(self) -> ICaseService:
        if self._case_service is None:
            raise RuntimeError("EvidenceService.case_service 未注入")
        return self._case_service

    @property
    def query_service(self) -> EvidenceQueryService:
        return self._query_service

    @property
    def mutation_service(self) -> EvidenceMutationService:
        return self._mutation_service

    @property
    def file_service(self) -> EvidenceFileService:
        return self._file_service

    @property
    def page_range_calculator(self) -> EvidencePageRangeCalculator:
        return self._page_range_calculator

    def create_evidence_list(self, case_id: int, title: str, user: Any | None = None) -> EvidenceList:
        case = self.mutation_service.require_case_model(case_service=self.case_service, case_id=case_id)
        return self.mutation_service.create_evidence_list(case=case, title=title, user=user)

    def validate_list_type_creation(self, case_id: int, list_type: str) -> tuple[bool, str | None, EvidenceList | None]:
        return self.mutation_service.validate_list_type_creation(case_id=case_id, list_type=list_type)

    def auto_link_previous_list(self, evidence_list: EvidenceList) -> EvidenceList | None:
        return self.mutation_service.auto_link_previous_list(evidence_list=evidence_list)

    def update_evidence_list(self, list_id: int, data: dict[str, Any]) -> EvidenceList:
        evidence_list = self.get_evidence_list(list_id)
        return self.mutation_service.update_evidence_list(evidence_list=evidence_list, title=data.get("title"))

    def delete_evidence_list(self, list_id: int) -> bool:
        evidence_list = self.get_evidence_list(list_id)
        return self.mutation_service.delete_evidence_list(evidence_list=evidence_list)

    def get_evidence_list(self, list_id: int) -> EvidenceList:
        return self.query_service.get_evidence_list(list_id)

    def list_evidence_lists(self, case_id: int) -> list[EvidenceList]:
        return self.query_service.list_evidence_lists(case_id)

    def create_evidence_item(self, list_id: int, data: dict[str, Any]) -> EvidenceItem:
        evidence_list = self.get_evidence_list(list_id)
        return self.mutation_service.create_evidence_item(
            evidence_list=evidence_list, name=data.get("name", ""), purpose=data.get("purpose", "")
        )

    def update_evidence_item(self, item_id: int, data: dict[str, Any]) -> EvidenceItem:
        item = self._get_evidence_item(item_id)
        return self.mutation_service.update_evidence_item(item=item, name=data.get("name"), purpose=data.get("purpose"))

    def delete_evidence_item(self, item_id: int) -> bool:
        item = self._get_evidence_item(item_id)
        return self.mutation_service.delete_evidence_item(item=item)

    def _get_evidence_item(self, item_id: int) -> EvidenceItem:
        return self.query_service.get_evidence_item(item_id)

    def reorder_items(self, list_id: int, item_ids: list[int]) -> bool:
        evidence_list = self.get_evidence_list(list_id)
        return self.mutation_service.reorder_items(evidence_list=evidence_list, item_ids=item_ids)

    def upload_file(self, item_id: int, file: Any) -> EvidenceItem:
        item = self._get_evidence_item(item_id)
        return self.file_service.upload_file(item=item, file=file)

    def delete_file(self, item_id: int) -> bool:
        item = self._get_evidence_item(item_id)
        return self.file_service.delete_file(item=item)

    def calculate_page_ranges(self, list_id: int) -> None:
        evidence_list = self.get_evidence_list(list_id)
        self.page_range_calculator.calculate_page_ranges(evidence_list=evidence_list)

    def recalculate_page_ranges_for_chain(self, list_id: int) -> None:
        self.page_range_calculator.recalculate_page_ranges_for_chain(list_id=list_id)

    def update_subsequent_lists_pages(self, case_id: int, start_order: int) -> None:
        self.page_range_calculator.update_subsequent_lists_pages(case_id=case_id, start_order=start_order)

    def calculate_start_order(self, evidence_list: EvidenceList) -> int:
        """
        计算证据清单的起始序号（从前置清单链推导）。

        遍历 previous_list 链表，累加每个前置清单的 items 数量。
        包含循环检测，检测到循环时返回默认值 1。
        """
        if not evidence_list.previous_list_id:
            return 1

        visited: set[int] = {evidence_list.pk}
        current: EvidenceList | None = evidence_list.previous_list
        total_items: int = 0

        while current is not None:
            if current.pk in visited:
                logger.info(
                    "calculate_start_order: 检测到循环引用, evidence_list_id=%s",
                    evidence_list.pk,
                )
                return 1
            visited.add(current.pk)
            total_items += current.items.count()
            if not current.previous_list_id:
                break
            current = current.previous_list

        return total_items + 1

    def calculate_start_page(self, evidence_list: EvidenceList) -> int:
        """
        计算证据清单的起始页码（从前置清单链推导）。

        遍历 previous_list 链表，累加每个前置清单的 total_pages。
        包含循环检测，检测到循环时返回默认值 1。
        """
        if not evidence_list.previous_list_id:
            return 1

        visited: set[int] = {evidence_list.pk}
        current: EvidenceList | None = evidence_list.previous_list
        total_pages: int = 0

        while current is not None:
            if current.pk in visited:
                logger.info(
                    "calculate_start_page: 检测到循环引用, evidence_list_id=%s",
                    evidence_list.pk,
                )
                return 1
            visited.add(current.pk)
            total_pages += current.total_pages
            if not current.previous_list_id:
                break
            current = current.previous_list

        return total_pages + 1

