"""documents/services/evidence/ 单元测试（evidence_export_service, evidence_mutation_service, evidence_service）。"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestListTypeEnum:
    """ListType 枚举测试。"""

    def test_choices_count(self) -> None:
        from apps.evidence.models import ListType
        assert len(ListType.choices) == 6

    def test_list_1_value(self) -> None:
        from apps.evidence.models import ListType
        assert ListType.LIST_1.value == "list_1"

    def test_list_6_label(self) -> None:
        from apps.evidence.models import ListType
        assert ListType.LIST_6.label == "证据清单六"


class TestListTypeOrder:
    """LIST_TYPE_ORDER 映射测试。"""

    def test_order_is_sequential(self) -> None:
        from apps.evidence.models import LIST_TYPE_ORDER, ListType
        for i, lt in enumerate([ListType.LIST_1, ListType.LIST_2, ListType.LIST_3,
                                ListType.LIST_4, ListType.LIST_5, ListType.LIST_6], 1):
            assert LIST_TYPE_ORDER[lt] == i

    def test_all_types_have_order(self) -> None:
        from apps.evidence.models import LIST_TYPE_ORDER, ListType
        for lt in ListType:
            assert lt in LIST_TYPE_ORDER


class TestListTypePrevious:
    """LIST_TYPE_PREVIOUS 映射测试。"""

    def test_list_1_has_no_previous(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None

    def test_list_2_previous_is_list_1(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1

    def test_list_6_previous_is_list_5(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5

    def test_chain_is_linear(self) -> None:
        from apps.evidence.models import LIST_TYPE_PREVIOUS, ListType
        current = ListType.LIST_6
        count = 0
        while current is not None:
            current = LIST_TYPE_PREVIOUS.get(current)  # type: ignore[assignment]
            count += 1
        assert count == 6


class TestMergeStatus:
    """MergeStatus 枚举测试。"""

    def test_values(self) -> None:
        from apps.evidence.models import MergeStatus
        assert MergeStatus.PENDING.value == "pending"
        assert MergeStatus.PROCESSING.value == "processing"
        assert MergeStatus.COMPLETED.value == "completed"
        assert MergeStatus.FAILED.value == "failed"

    def test_choices_count(self) -> None:
        from apps.evidence.models import MergeStatus
        assert len(MergeStatus.choices) == 4


class TestEvidenceItemPageRangeDisplay:
    """EvidenceItem.page_range_display 属性测试。"""

    def _make_item(self, page_start=None, page_end=None):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.page_start = page_start
        item.page_end = page_end
        return item

    def test_both_none(self) -> None:
        item = self._make_item(None, None)
        assert item.page_range_display == "-"

    def test_same_page(self) -> None:
        item = self._make_item(5, 5)
        assert item.page_range_display == "5"

    def test_range(self) -> None:
        item = self._make_item(3, 7)
        assert item.page_range_display == "3-7"

    def test_only_start(self) -> None:
        item = self._make_item(3, None)
        assert item.page_range_display == "-"


class TestEvidenceItemFileSizeDisplay:
    """EvidenceItem.file_size_display 属性测试。"""

    def _make_item(self, file_size=0):
        from apps.evidence.models import EvidenceItem
        item = EvidenceItem.__new__(EvidenceItem)
        item.file_size = file_size
        return item

    def test_zero(self) -> None:
        assert self._make_item(0).file_size_display == "-"

    def test_bytes(self) -> None:
        assert self._make_item(500).file_size_display == "500 B"

    def test_kilobytes(self) -> None:
        result = self._make_item(2048).file_size_display
        assert "KB" in result
        assert "2.0" in result

    def test_megabytes(self) -> None:
        result = self._make_item(2 * 1024 * 1024).file_size_display
        assert "MB" in result


class TestEvidenceServiceCalculateStartOrder:
    """EvidenceService.calculate_start_order 测试。"""

    def _make_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        return EvidenceService(
            case_service=MagicMock(),
            query_service=MagicMock(),
            mutation_service=MagicMock(),
            file_service=MagicMock(),
        )

    def test_no_previous_list_returns_1(self) -> None:
        svc = self._make_service()
        el = MagicMock()
        el.previous_list_id = None
        assert svc.calculate_start_order(el) == 1

    def test_with_previous_list(self) -> None:
        svc = self._make_service()
        prev = MagicMock()
        prev.pk = 10
        prev.previous_list_id = None
        prev.items.count.return_value = 5

        el = MagicMock()
        el.pk = 20
        el.previous_list_id = 10
        el.previous_list = prev

        assert svc.calculate_start_order(el) == 6

    def test_circular_reference_returns_1(self) -> None:
        svc = self._make_service()
        el = MagicMock()
        el.pk = 1
        el.previous_list_id = 2

        prev = MagicMock()
        prev.pk = 2
        prev.previous_list_id = 1
        prev.previous_list = el
        prev.items.count.return_value = 3

        el.previous_list = prev

        assert svc.calculate_start_order(el) == 1


class TestEvidenceServiceCalculateStartPage:
    """EvidenceService.calculate_start_page 测试。"""

    def _make_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        return EvidenceService(
            case_service=MagicMock(),
            query_service=MagicMock(),
            mutation_service=MagicMock(),
            file_service=MagicMock(),
        )

    def test_no_previous_returns_1(self) -> None:
        svc = self._make_service()
        el = MagicMock()
        el.previous_list_id = None
        assert svc.calculate_start_page(el) == 1

    def test_with_previous_pages(self) -> None:
        svc = self._make_service()
        prev = MagicMock()
        prev.pk = 10
        prev.previous_list_id = None
        prev.total_pages = 15

        el = MagicMock()
        el.pk = 20
        el.previous_list_id = 10
        el.previous_list = prev

        assert svc.calculate_start_page(el) == 16

    def test_circular_reference_returns_1(self) -> None:
        svc = self._make_service()
        el = MagicMock()
        el.pk = 1
        el.previous_list_id = 2

        prev = MagicMock()
        prev.pk = 2
        prev.previous_list_id = 1
        prev.previous_list = el
        prev.total_pages = 10

        el.previous_list = prev

        assert svc.calculate_start_page(el) == 1


class TestEvidenceServiceDelegation:
    """EvidenceService 委托方法测试。"""

    def _make_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        qs = MagicMock()
        ms = MagicMock()
        fs = MagicMock()
        cs = MagicMock()
        return EvidenceService(
            case_service=cs,
            query_service=qs,
            mutation_service=ms,
            file_service=fs,
        ), qs, ms, fs, cs

    def test_get_evidence_list_delegates(self) -> None:
        svc, qs, _, _, _ = self._make_service()
        svc.get_evidence_list(42)
        qs.get_evidence_list.assert_called_once_with(42)

    def test_list_evidence_lists_delegates(self) -> None:
        svc, qs, _, _, _ = self._make_service()
        svc.list_evidence_lists(1)
        qs.list_evidence_lists.assert_called_once_with(1)

    def test_delete_evidence_item_delegates(self) -> None:
        svc, qs, ms, _, _ = self._make_service()
        svc.delete_evidence_item(5)
        qs.get_evidence_item.assert_called_once_with(5)
        ms.delete_evidence_item.assert_called_once()

    def test_upload_file_delegates(self) -> None:
        svc, qs, _, fs, _ = self._make_service()
        file_mock = MagicMock()
        svc.upload_file(7, file_mock)
        fs.upload_file.assert_called_once()

    def test_case_service_not_injected_raises(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service
