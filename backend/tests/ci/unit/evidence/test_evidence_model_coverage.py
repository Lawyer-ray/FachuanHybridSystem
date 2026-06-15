"""Tests for evidence model (apps.evidence.models.evidence) — comprehensive branch coverage.

Covers: EvidenceList and EvidenceItem model properties, MergeStatus, ListType,
end_page, page_range_display, order_range_display, item page_range_display,
file_size_display branches, factory functions.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ---------------------------------------------------------------------------
# Choice enums
# ---------------------------------------------------------------------------

class TestMergeStatusChoices:
    def test_choices(self):
        from apps.evidence.models.evidence import MergeStatus
        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.PROCESSING == "processing"
        assert MergeStatus.COMPLETED == "completed"
        assert MergeStatus.FAILED == "failed"
        assert len(MergeStatus.choices) == 4


class TestListTypeChoices:
    def test_choices(self):
        from apps.evidence.models.evidence import ListType
        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"
        assert len(ListType.choices) == 6


class TestListTypeOrderAndPrevious:
    def test_order_dict_complete(self):
        from apps.evidence.models.evidence import LIST_TYPE_ORDER, ListType
        for lt in ListType:
            assert lt in LIST_TYPE_ORDER
        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1
        assert LIST_TYPE_ORDER[ListType.LIST_6] == 6

    def test_previous_dict_chain(self):
        from apps.evidence.models.evidence import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5


# ---------------------------------------------------------------------------
# EvidenceList properties
# ---------------------------------------------------------------------------


def _make_evidence_list():
    """Build an EvidenceList instance without DB."""
    from apps.evidence.models.evidence import EvidenceList
    obj = EvidenceList.__new__(EvidenceList)
    obj.total_pages = 0
    obj.item_count = None
    return obj


class TestEvidenceListEndPage:
    def test_zero_pages(self):
        el = _make_evidence_list()
        with patch.object(type(el), 'start_page', new_callable=PropertyMock, return_value=1):
            assert el.end_page == 1

    def test_positive_pages(self):
        el = _make_evidence_list()
        el.total_pages = 5
        with patch.object(type(el), 'start_page', new_callable=PropertyMock, return_value=3):
            assert el.end_page == 7


class TestEvidenceListPageRangeDisplay:
    def test_zero_pages_returns_empty(self):
        el = _make_evidence_list()
        el.total_pages = 0
        assert el.page_range_display == ""

    def test_positive_pages(self):
        el = _make_evidence_list()
        el.total_pages = 3
        with patch.object(type(el), 'start_page', new_callable=PropertyMock, return_value=2):
            assert el.page_range_display == "2-4"


class TestEvidenceListOrderRangeDisplay:
    def test_zero_items_with_item_count(self):
        el = _make_evidence_list()
        el.item_count = 0
        with patch.object(type(el), 'start_order', new_callable=PropertyMock, return_value=1):
            assert el.order_range_display == "-"

    def test_no_item_count_attr_uses_items_count(self):
        el = _make_evidence_list()
        if hasattr(el, 'item_count'):
            del el.item_count
        mock_items = MagicMock()
        mock_items.count.return_value = 3
        type(el).items = mock_items  # type: ignore[assignment]
        with patch.object(type(el), 'start_order', new_callable=PropertyMock, return_value=2):
            assert el.order_range_display == "2-4"

    def test_single_item(self):
        el = _make_evidence_list()
        el.item_count = 1
        with patch.object(type(el), 'start_order', new_callable=PropertyMock, return_value=5):
            assert el.order_range_display == "5"

    def test_multiple_items(self):
        el = _make_evidence_list()
        el.item_count = 3
        with patch.object(type(el), 'start_order', new_callable=PropertyMock, return_value=2):
            assert el.order_range_display == "2-4"

    def test_item_count_is_none_fallback(self):
        el = _make_evidence_list()
        el.item_count = None
        mock_items = MagicMock()
        mock_items.count.return_value = 2
        type(el).items = mock_items  # type: ignore[assignment]
        with patch.object(type(el), 'start_order', new_callable=PropertyMock, return_value=1):
            assert el.order_range_display == "1-2"


class TestEvidenceListStr:
    def test_str(self):
        el = _make_evidence_list()
        mock_case = MagicMock()
        mock_case.name = "张三案"
        type(el).case = mock_case  # type: ignore[assignment]
        el.title = "证据清单一"
        assert str(el) == "张三案 - 证据清单一"


# ---------------------------------------------------------------------------
# EvidenceItem properties
# ---------------------------------------------------------------------------


def _make_evidence_item():
    from apps.evidence.models.evidence import EvidenceItem
    obj = EvidenceItem.__new__(EvidenceItem)
    return obj


class TestEvidenceItemPageRangeDisplay:
    def test_none_start(self):
        item = _make_evidence_item()
        item.page_start = None
        item.page_end = 5
        assert item.page_range_display == "-"

    def test_none_end(self):
        item = _make_evidence_item()
        item.page_start = 1
        item.page_end = None
        assert item.page_range_display == "-"

    def test_both_none(self):
        item = _make_evidence_item()
        item.page_start = None
        item.page_end = None
        assert item.page_range_display == "-"

    def test_single_page(self):
        item = _make_evidence_item()
        item.page_start = 3
        item.page_end = 3
        assert item.page_range_display == "3"

    def test_range(self):
        item = _make_evidence_item()
        item.page_start = 1
        item.page_end = 5
        assert item.page_range_display == "1-5"


class TestEvidenceItemFileSizeDisplay:
    def test_zero(self):
        item = _make_evidence_item()
        item.file_size = 0
        assert item.file_size_display == "-"

    def test_bytes(self):
        item = _make_evidence_item()
        item.file_size = 500
        assert item.file_size_display == "500 B"

    def test_kilobytes(self):
        item = _make_evidence_item()
        item.file_size = 2048
        assert item.file_size_display == "2.0 KB"

    def test_megabytes(self):
        item = _make_evidence_item()
        item.file_size = 2 * 1024 * 1024
        assert item.file_size_display == "2.0 MB"

    def test_boundary_1023_bytes(self):
        item = _make_evidence_item()
        item.file_size = 1023
        assert item.file_size_display == "1023 B"

    def test_boundary_1024_bytes(self):
        item = _make_evidence_item()
        item.file_size = 1024
        assert item.file_size_display == "1.0 KB"

    def test_boundary_1mb(self):
        item = _make_evidence_item()
        item.file_size = 1024 * 1024
        assert item.file_size_display == "1.0 MB"


class TestEvidenceItemStr:
    def test_str(self):
        item = _make_evidence_item()
        item.order = 3
        item.name = "合同"
        assert str(item) == "3. 合同"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


class TestGetEvidenceService:
    def test_returns_service_instance(self):
        from apps.evidence.models.evidence import _get_evidence_service
        svc = _get_evidence_service()
        assert svc is not None
        assert hasattr(svc, 'calculate_start_order')


class TestGetEvidenceStorage:
    def test_returns_storage(self):
        from apps.evidence.models.evidence import _get_evidence_storage
        storage = _get_evidence_storage()
        assert storage is not None
