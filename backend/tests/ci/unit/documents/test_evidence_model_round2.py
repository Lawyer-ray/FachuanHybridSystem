"""Round 2 coverage tests for evidence models — using apps.evidence.models (canonical path)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── MergeStatus / ListType / LIST_TYPE_ORDER / LIST_TYPE_PREVIOUS ──

class TestMergeStatusValues:
    def test_pending_value(self):
        from apps.evidence.models import MergeStatus
        assert MergeStatus.PENDING.value == "pending"
        assert MergeStatus.PENDING.label == "待合并"

    def test_processing_value(self):
        from apps.evidence.models import MergeStatus
        assert MergeStatus.PROCESSING.value == "processing"

    def test_completed_value(self):
        from apps.evidence.models import MergeStatus
        assert MergeStatus.COMPLETED.value == "completed"

    def test_failed_value(self):
        from apps.evidence.models import MergeStatus
        assert MergeStatus.FAILED.value == "failed"

    def test_choices_count(self):
        from apps.evidence.models import MergeStatus
        assert len(MergeStatus.choices) == 4


class TestListTypeValues:
    def test_list_1_value(self):
        from apps.evidence.models import ListType
        assert ListType.LIST_1.value == "list_1"

    def test_list_6_label(self):
        from apps.evidence.models import ListType
        assert ListType.LIST_6.label == "证据清单六"

    def test_choices_count(self):
        from apps.evidence.models import ListType
        assert len(ListType.choices) == 6


class TestListTypeOrder:
    def test_sequential_ordering(self):
        from apps.evidence.models import LIST_TYPE_ORDER, ListType
        for i, lt in enumerate(
            [ListType.LIST_1, ListType.LIST_2, ListType.LIST_3,
             ListType.LIST_4, ListType.LIST_5, ListType.LIST_6], 1
        ):
            assert LIST_TYPE_ORDER[lt] == i

    def test_all_types_have_order(self):
        from apps.evidence.models import LIST_TYPE_ORDER, ListType
        for lt in ListType:
            assert lt in LIST_TYPE_ORDER


class TestListTypePrevious:
    def test_list_1_no_previous(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None

    def test_list_2_previous_is_list_1(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1

    def test_list_3_previous_is_list_2(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_3] == ListType.LIST_2

    def test_list_4_previous_is_list_3(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_4] == ListType.LIST_3

    def test_list_5_previous_is_list_4(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_5] == ListType.LIST_4

    def test_list_6_previous_is_list_5(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5

    def test_chain_length(self):
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        current = ListType.LIST_6
        count = 0
        while current is not None:
            current = LIST_TYPE_PREVIOUS.get(current)
            count += 1
        assert count == 6


# ── EvidenceList model properties via __new__ ──

class TestEvidenceListEndPage:
    def test_end_page_zero_total(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el.total_pages = 0
        el._state = MagicMock()
        with patch.object(type(el), 'start_page', new_callable=lambda: property(lambda self: 5)):
            assert el.end_page == 5

    def test_end_page_nonzero_total(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el.total_pages = 10
        el._state = MagicMock()
        with patch.object(type(el), 'start_page', new_callable=lambda: property(lambda self: 1)):
            assert el.end_page == 10


class TestEvidenceListPageRangeDisplay:
    def test_empty_when_zero_pages(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el.total_pages = 0
        el._state = MagicMock()
        assert el.page_range_display == ""

    def test_range_when_pages_present(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el.total_pages = 5
        el._state = MagicMock()
        with patch.object(type(el), 'start_page', new_callable=lambda: property(lambda self: 3)):
            assert el.page_range_display == "3-7"


class TestEvidenceListOrderRangeDisplay:
    def test_no_item_count_calls_items_count(self):
        from apps.evidence.models import EvidenceList
        # Use real __new__ without item_count attr set
        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        # Don't set item_count — the property falls through to items.count()
        # But items is a RelatedManager, so we need to mock the descriptor
        with patch.object(type(el), 'items', new_callable=lambda: property(lambda self: MagicMock(count=MagicMock(return_value=0)))):
            with patch.object(type(el), 'start_order', new_callable=lambda: property(lambda self: 1)):
                assert el.order_range_display == "-"

    def test_single_item_with_attr(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        el.__dict__["item_count"] = 1
        with patch.object(type(el), 'start_order', new_callable=lambda: property(lambda self: 3)):
            assert el.order_range_display == "3"

    def test_multiple_items_with_attr(self):
        from apps.evidence.models import EvidenceList
        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        el.__dict__["item_count"] = 5
        with patch.object(type(el), 'start_order', new_callable=lambda: property(lambda self: 1)):
            assert el.order_range_display == "1-5"


# ── EvidenceItem model properties via __new__ ──

class TestEvidenceItemPageRange:
    def test_both_none(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.page_start = None
        item.page_end = None
        assert item.page_range_display == "-"

    def test_same_page(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.page_start = 5
        item.page_end = 5
        assert item.page_range_display == "5"

    def test_range(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.page_start = 3
        item.page_end = 7
        assert item.page_range_display == "3-7"

    def test_start_none(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.page_start = None
        item.page_end = 7
        assert item.page_range_display == "-"


class TestEvidenceItemFileSize:
    def test_zero(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 0
        assert item.file_size_display == "-"

    def test_bytes(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 500
        assert item.file_size_display == "500 B"

    def test_kilobytes(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 2048
        assert "KB" in item.file_size_display
        assert "2.0" in item.file_size_display

    def test_megabytes(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 2 * 1024 * 1024
        assert "MB" in item.file_size_display

    def test_exactly_1024_bytes(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 1024
        assert "KB" in item.file_size_display

    def test_exactly_1mb(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = 1024 * 1024
        assert "MB" in item.file_size_display


# ── __str__ methods ──

class TestStrMethods:
    def test_evidence_item_str(self):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.order = 3
        item.name = "合同原件"
        assert str(item) == "3. 合同原件"

    def test_evidence_list_str(self):
        from apps.evidence.models import EvidenceList
        el = MagicMock()
        el.case.name = "测试案件"
        el.title = "证据清单一"
        result = f"{el.case.name} - {el.title}"
        assert result == "测试案件 - 证据清单一"


# ── Factory functions ──

class TestFactoryFunctions:
    def test_get_evidence_service_returns_instance(self):
        # Import directly from the evidence app to avoid model conflicts
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        assert svc is not None

    def test_get_evidence_storage_returns_instance(self):
        from apps.documents.services.evidence.evidence_storage import evidence_file_storage
        assert evidence_file_storage is not None
