"""apps.evidence.models 枚举与模型属性单元测试（ListType / MergeStatus / EvidenceItem）。"""

from __future__ import annotations


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
