"""Tests for evidence list models (EvidenceList, EvidenceItem, ListType, MergeStatus).

Uses apps.evidence.models as the canonical import path to avoid model registration
conflicts between apps.documents.models.evidence and apps.evidence.models.evidence.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.evidence.models import EvidenceList, EvidenceItem, ListType, MergeStatus


class TestMergeStatusChoices:
    def test_pending(self) -> None:
        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.PENDING.label == "待合并"

    def test_all_values(self) -> None:
        assert MergeStatus.PROCESSING == "processing"
        assert MergeStatus.COMPLETED == "completed"
        assert MergeStatus.FAILED == "failed"

    def test_choices_count(self) -> None:
        assert len(MergeStatus.choices) == 4


class TestListTypeChoices:
    def test_first_and_last(self) -> None:
        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"

    def test_all_six(self) -> None:
        assert len(ListType.choices) == 6

    def test_list_type_order_mapping(self) -> None:
        """Test the LIST_TYPE_ORDER dict from the evidence module."""
        from apps.evidence.models.evidence import LIST_TYPE_ORDER

        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1
        assert LIST_TYPE_ORDER[ListType.LIST_6] == 6
        assert len(LIST_TYPE_ORDER) == 6

    def test_list_type_previous_chain(self) -> None:
        from apps.evidence.models.evidence import LIST_TYPE_PREVIOUS

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1
        assert LIST_TYPE_PREVIOUS[ListType.LIST_3] == ListType.LIST_2
        assert LIST_TYPE_PREVIOUS[ListType.LIST_4] == ListType.LIST_3
        assert LIST_TYPE_PREVIOUS[ListType.LIST_5] == ListType.LIST_4
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5


class TestEvidenceListEndPage:
    def test_zero_total_pages(self) -> None:
        obj = SimpleNamespace(total_pages=0, start_page=5)
        assert EvidenceList.end_page.fget(obj) == 5  # type: ignore[arg-type]

    def test_nonzero_total_pages(self) -> None:
        obj = SimpleNamespace(total_pages=3, start_page=5)
        assert EvidenceList.end_page.fget(obj) == 7  # type: ignore[arg-type]

    def test_one_page(self) -> None:
        obj = SimpleNamespace(total_pages=1, start_page=10)
        assert EvidenceList.end_page.fget(obj) == 10  # type: ignore[arg-type]


class TestEvidenceListPageRangeDisplay:
    def test_empty_when_zero_pages(self) -> None:
        obj = SimpleNamespace(total_pages=0)
        assert EvidenceList.page_range_display.fget(obj) == ""  # type: ignore[arg-type]

    def test_range_display(self) -> None:
        # page_range_display calls self.start_page and self.end_page
        obj = SimpleNamespace(total_pages=5, start_page=3, end_page=7)
        assert EvidenceList.page_range_display.fget(obj) == "3-7"  # type: ignore[arg-type]


class TestEvidenceListOrderRangeDisplay:
    def test_no_items(self) -> None:
        obj = SimpleNamespace(item_count=0, start_order=1)
        assert EvidenceList.order_range_display.fget(obj) == "-"  # type: ignore[arg-type]

    def test_single_item(self) -> None:
        obj = SimpleNamespace(item_count=1, start_order=3)
        assert EvidenceList.order_range_display.fget(obj) == "3"  # type: ignore[arg-type]

    def test_range(self) -> None:
        obj = SimpleNamespace(item_count=5, start_order=1)
        assert EvidenceList.order_range_display.fget(obj) == "1-5"  # type: ignore[arg-type]

    def test_no_item_count_attr_uses_items(self) -> None:
        """When item_count is not set, falls back to self.items.count()."""
        mock_items = MagicMock()
        mock_items.count.return_value = 3
        obj = SimpleNamespace(start_order=10, items=mock_items)
        assert EvidenceList.order_range_display.fget(obj) == "10-12"  # type: ignore[arg-type]


class TestEvidenceListStr:
    def test_str(self) -> None:
        case = SimpleNamespace(name="测试案件")
        obj = SimpleNamespace(case=case, title="证据清单一")
        assert EvidenceList.__str__(obj) == "测试案件 - 证据清单一"  # type: ignore[arg-type]


class TestEvidenceItemPageRangeDisplay:
    def test_none_pages(self) -> None:
        obj = SimpleNamespace(page_start=None, page_end=None)
        assert EvidenceItem.page_range_display.fget(obj) == "-"  # type: ignore[arg-type]

    def test_same_page(self) -> None:
        obj = SimpleNamespace(page_start=3, page_end=3)
        assert EvidenceItem.page_range_display.fget(obj) == "3"  # type: ignore[arg-type]

    def test_page_range(self) -> None:
        obj = SimpleNamespace(page_start=1, page_end=5)
        assert EvidenceItem.page_range_display.fget(obj) == "1-5"  # type: ignore[arg-type]


class TestEvidenceItemFileSizeDisplay:
    def test_zero(self) -> None:
        obj = SimpleNamespace(file_size=0)
        assert EvidenceItem.file_size_display.fget(obj) == "-"  # type: ignore[arg-type]

    def test_bytes(self) -> None:
        obj = SimpleNamespace(file_size=512)
        assert EvidenceItem.file_size_display.fget(obj) == "512 B"  # type: ignore[arg-type]

    def test_kb(self) -> None:
        obj = SimpleNamespace(file_size=2048)
        assert EvidenceItem.file_size_display.fget(obj) == "2.0 KB"  # type: ignore[arg-type]

    def test_mb(self) -> None:
        obj = SimpleNamespace(file_size=2 * 1024 * 1024)
        assert EvidenceItem.file_size_display.fget(obj) == "2.0 MB"  # type: ignore[arg-type]


class TestEvidenceItemStr:
    def test_str(self) -> None:
        obj = SimpleNamespace(order=1, name="合同原件")
        assert EvidenceItem.__str__(obj) == "1. 合同原件"  # type: ignore[arg-type]
