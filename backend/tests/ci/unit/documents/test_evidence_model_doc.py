"""Tests for apps.documents.models.evidence — the backward-compat shim module.

This file is a migration shim; the actual model classes live in
apps.evidence.models.evidence and are accessed via __getattr__.

Covers:
  - MergeStatus, ListType, LIST_TYPE_ORDER, LIST_TYPE_PREVIOUS (locally defined)
  - _get_evidence_service(), _get_evidence_storage() factory functions
  - The __getattr__ delegation path from apps.documents.models
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# __getattr__ delegation — verify documents.models can resolve evidence names
# ---------------------------------------------------------------------------


class TestDocumentsModelsGetattrDelegation:
    """Verify apps.documents.models.__getattr__ redirects evidence names."""

    def test_evidence_list_from_documents_models(self) -> None:
        from apps.evidence.models import EvidenceList

        assert EvidenceList is not None

    def test_evidence_item_from_documents_models(self) -> None:
        from apps.evidence.models import EvidenceItem

        assert EvidenceItem is not None

    def test_merge_status_from_documents_models(self) -> None:
        from apps.evidence.models import MergeStatus

        assert MergeStatus.PENDING == "pending"

    def test_list_type_from_documents_models(self) -> None:
        from apps.evidence.models import ListType

        assert ListType.LIST_1 == "list_1"

    def test_list_type_order_from_documents_models(self) -> None:
        from apps.evidence.models import LIST_TYPE_ORDER, ListType

        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1

    def test_list_type_previous_from_documents_models(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None


# ---------------------------------------------------------------------------
# MergeStatus choices
# ---------------------------------------------------------------------------


class TestDocumentsMergeStatus:
    def test_all_values(self) -> None:
        from apps.evidence.models import MergeStatus

        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.PROCESSING == "processing"
        assert MergeStatus.COMPLETED == "completed"
        assert MergeStatus.FAILED == "failed"
        assert len(MergeStatus.choices) == 4


# ---------------------------------------------------------------------------
# ListType choices and ordering dicts
# ---------------------------------------------------------------------------


class TestDocumentsListType:
    def test_all_values(self) -> None:
        from apps.evidence.models import ListType

        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"
        assert len(ListType.choices) == 6


class TestDocumentsListTypeOrder:
    def test_order_covers_all(self) -> None:
        from apps.evidence.models import LIST_TYPE_ORDER, ListType

        for lt in ListType:
            assert lt in LIST_TYPE_ORDER
        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1
        assert LIST_TYPE_ORDER[ListType.LIST_6] == 6


class TestDocumentsListTypePrevious:
    def test_chain(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1
        assert LIST_TYPE_PREVIOUS[ListType.LIST_3] == ListType.LIST_2
        assert LIST_TYPE_PREVIOUS[ListType.LIST_4] == ListType.LIST_3
        assert LIST_TYPE_PREVIOUS[ListType.LIST_5] == ListType.LIST_4
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5


# ---------------------------------------------------------------------------
# Factory functions (from apps.documents.models.evidence)
# ---------------------------------------------------------------------------


class TestGetEvidenceService:
    def test_returns_service_instance(self) -> None:
        from apps.evidence.models.evidence import _get_evidence_service

        svc = _get_evidence_service()
        assert svc is not None
        assert hasattr(svc, "calculate_start_order")


class TestGetEvidenceStorage:
    def test_returns_storage(self) -> None:
        from apps.evidence.models.evidence import _get_evidence_storage

        storage = _get_evidence_storage()
        assert storage is not None


# ---------------------------------------------------------------------------
# EvidenceList properties (using __new__ to avoid DB)
# ---------------------------------------------------------------------------


def _make_evidence_list():
    from apps.evidence.models import EvidenceList

    obj = EvidenceList.__new__(EvidenceList)
    obj.total_pages = 0
    obj.item_count = None
    return obj


class TestDocumentsEvidenceListStr:
    def test_str(self) -> None:
        el = _make_evidence_list()
        mock_case = MagicMock()
        mock_case.name = "张三案"
        type(el).case = mock_case  # type: ignore[assignment]
        el.title = "证据清单一"
        assert str(el) == "张三案 - 证据清单一"


class TestDocumentsEvidenceListEndPage:
    def test_zero_pages(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        with patch.object(type(el), "start_page", new_callable=PropertyMock, return_value=1):
            assert el.end_page == 1

    def test_positive_pages(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.total_pages = 5
        with patch.object(type(el), "start_page", new_callable=PropertyMock, return_value=3):
            assert el.end_page == 7


class TestDocumentsEvidenceListPageRangeDisplay:
    def test_zero_pages_returns_empty(self) -> None:
        el = _make_evidence_list()
        el.total_pages = 0
        assert el.page_range_display == ""

    def test_positive_pages(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.total_pages = 3
        with patch.object(type(el), "start_page", new_callable=PropertyMock, return_value=2):
            assert el.page_range_display == "2-4"


class TestDocumentsEvidenceListOrderRangeDisplay:
    def test_zero_items_with_item_count(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.item_count = 0
        with patch.object(type(el), "start_order", new_callable=PropertyMock, return_value=1):
            assert el.order_range_display == "-"

    def test_single_item(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.item_count = 1
        with patch.object(type(el), "start_order", new_callable=PropertyMock, return_value=5):
            assert el.order_range_display == "5"

    def test_multiple_items(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.item_count = 3
        with patch.object(type(el), "start_order", new_callable=PropertyMock, return_value=2):
            assert el.order_range_display == "2-4"

    def test_item_count_none_fallback(self) -> None:
        from unittest.mock import PropertyMock

        el = _make_evidence_list()
        el.item_count = None
        mock_items = MagicMock()
        mock_items.count.return_value = 2
        type(el).items = mock_items  # type: ignore[assignment]
        with patch.object(type(el), "start_order", new_callable=PropertyMock, return_value=1):
            assert el.order_range_display == "1-2"


# ---------------------------------------------------------------------------
# EvidenceItem properties
# ---------------------------------------------------------------------------


def _make_evidence_item():
    from apps.evidence.models import EvidenceItem

    return EvidenceItem.__new__(EvidenceItem)


class TestDocumentsEvidenceItemStr:
    def test_str(self) -> None:
        item = _make_evidence_item()
        item.order = 3
        item.name = "合同"
        assert str(item) == "3. 合同"


class TestDocumentsEvidenceItemPageRangeDisplay:
    def test_both_none(self) -> None:
        item = _make_evidence_item()
        item.page_start = None
        item.page_end = None
        assert item.page_range_display == "-"

    def test_none_start(self) -> None:
        item = _make_evidence_item()
        item.page_start = None
        item.page_end = 5
        assert item.page_range_display == "-"

    def test_none_end(self) -> None:
        item = _make_evidence_item()
        item.page_start = 1
        item.page_end = None
        assert item.page_range_display == "-"

    def test_single_page(self) -> None:
        item = _make_evidence_item()
        item.page_start = 3
        item.page_end = 3
        assert item.page_range_display == "3"

    def test_range(self) -> None:
        item = _make_evidence_item()
        item.page_start = 1
        item.page_end = 5
        assert item.page_range_display == "1-5"


class TestDocumentsEvidenceItemFileSizeDisplay:
    def test_zero(self) -> None:
        item = _make_evidence_item()
        item.file_size = 0
        assert item.file_size_display == "-"

    def test_bytes(self) -> None:
        item = _make_evidence_item()
        item.file_size = 500
        assert item.file_size_display == "500 B"

    def test_kilobytes(self) -> None:
        item = _make_evidence_item()
        item.file_size = 2048
        assert item.file_size_display == "2.0 KB"

    def test_megabytes(self) -> None:
        item = _make_evidence_item()
        item.file_size = 2 * 1024 * 1024
        assert item.file_size_display == "2.0 MB"

    def test_boundary_1023_bytes(self) -> None:
        item = _make_evidence_item()
        item.file_size = 1023
        assert item.file_size_display == "1023 B"

    def test_boundary_1024_bytes(self) -> None:
        item = _make_evidence_item()
        item.file_size = 1024
        assert item.file_size_display == "1.0 KB"

    def test_boundary_1mb(self) -> None:
        item = _make_evidence_item()
        item.file_size = 1024 * 1024
        assert item.file_size_display == "1.0 MB"
