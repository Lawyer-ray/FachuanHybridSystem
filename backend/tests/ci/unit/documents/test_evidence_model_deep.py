"""Unit tests for documents.models.evidence — EvidenceList & EvidenceItem."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.cases.models import Case
from apps.client.models import Client
from apps.contracts.models import Contract
from apps.core.models.enums import SimpleCaseType
from apps.evidence.models import EvidenceItem, EvidenceList, ListType, MergeStatus
from apps.testing.factories import CaseFactory, ContractFactory


@pytest.mark.django_db
class TestEvidenceListChoices:
    def test_merge_status_values(self):
        assert MergeStatus.PENDING.value == "pending"
        assert MergeStatus.PROCESSING.value == "processing"
        assert MergeStatus.COMPLETED.value == "completed"
        assert MergeStatus.FAILED.value == "failed"

    def test_list_type_values(self):
        assert ListType.LIST_1.value == "list_1"
        assert ListType.LIST_6.value == "list_6"

    def test_all_list_types_count(self):
        assert len(ListType) == 6


@pytest.mark.django_db
class TestEvidenceListStr:
    def test_str(self):
        case = CaseFactory(name="张三诉李四")
        el = EvidenceList.objects.create(case=case, title="证据清单一", list_type=ListType.LIST_1)
        assert str(el) == "张三诉李四 - 证据清单一"

    def test_str_empty_title(self):
        case = CaseFactory(name="空标题案件")
        el = EvidenceList.objects.create(case=case, title="", list_type=ListType.LIST_2)
        assert "空标题案件" in str(el)


@pytest.mark.django_db
class TestEvidenceListEndPage:
    def test_end_page_zero_total_pages(self):
        """end_page == start_page when total_pages == 0."""
        el = EvidenceList(total_pages=0)
        assert el.end_page == el.start_page

    def test_end_page_nonzero_total_pages(self):
        """end_page = start_page + total_pages - 1."""
        el = EvidenceList(total_pages=5)
        # start_page delegates to service; mock it
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 10
            assert el.end_page == 14  # 10 + 5 - 1


@pytest.mark.django_db
class TestEvidenceListPageRangeDisplay:
    def test_empty_when_zero_total(self):
        el = EvidenceList(total_pages=0)
        assert el.page_range_display == ""

    def test_range_display(self):
        el = EvidenceList(total_pages=3)
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 5
            assert el.page_range_display == "5-7"


@pytest.mark.django_db
class TestEvidenceListOrderRangeDisplay:
    def test_empty_items_returns_dash(self):
        case = CaseFactory(name="空案件")
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        # 无 item → order_range_display = "-"
        assert el.order_range_display == "-"

    def test_single_item(self):
        case = CaseFactory(name="单条目案件")
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        EvidenceItem.objects.create(evidence_list=el, order=1, name="合同", purpose="证明")
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 1
            assert el.order_range_display == "1"

    def test_multiple_items(self):
        case = CaseFactory(name="多条目案件")
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        for i in range(1, 4):
            EvidenceItem.objects.create(evidence_list=el, order=i, name=f"证据{i}", purpose="证明")
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 3
            assert el.order_range_display == "3-5"

    def test_uses_item_count_attribute_if_set(self):
        """When item_count attr is set, it avoids an extra query."""
        el = EvidenceList()
        el.item_count = 2  # type: ignore[attr-defined]
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 10
            assert el.order_range_display == "10-11"


@pytest.mark.django_db
class TestEvidenceListStartOrderAndPage:
    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_order_delegates_to_service(self, mock_svc):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        mock_svc.return_value.calculate_start_order.return_value = 7
        assert el.start_order == 7

    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_page_delegates_to_service(self, mock_svc):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        mock_svc.return_value.calculate_start_page.return_value = 1
        assert el.start_page == 1


@pytest.mark.django_db
class TestEvidenceListMeta:
    def test_unique_constraint(self):
        """同一案件不能有两个相同 list_type 的 EvidenceList."""
        case = CaseFactory()
        EvidenceList.objects.create(case=case, title="清单一", list_type=ListType.LIST_1)
        with pytest.raises(Exception):
            EvidenceList.objects.create(case=case, title="清单二", list_type=ListType.LIST_1)


@pytest.mark.django_db
class TestEvidenceItemStr:
    def test_str(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(evidence_list=el, order=3, name="转账记录", purpose="证明付款")
        assert str(item) == "3. 转账记录"


@pytest.mark.django_db
class TestEvidenceItemPageRangeDisplay:
    def test_none_pages(self):
        item = EvidenceItem(page_start=None, page_end=None)
        assert item.page_range_display == "-"

    def test_single_page(self):
        item = EvidenceItem(page_start=5, page_end=5)
        assert item.page_range_display == "5"

    def test_range(self):
        item = EvidenceItem(page_start=1, page_end=10)
        assert item.page_range_display == "1-10"

    def test_page_start_only(self):
        item = EvidenceItem(page_start=1, page_end=None)
        assert item.page_range_display == "-"

    def test_page_end_only(self):
        item = EvidenceItem(page_start=None, page_end=5)
        assert item.page_range_display == "-"


@pytest.mark.django_db
class TestEvidenceItemFileSizeDisplay:
    def test_zero(self):
        assert EvidenceItem(file_size=0).file_size_display == "-"

    def test_bytes(self):
        assert EvidenceItem(file_size=500).file_size_display == "500 B"

    def test_kilobytes(self):
        assert EvidenceItem(file_size=2048).file_size_display == "2.0 KB"

    def test_exact_kilobyte_boundary(self):
        assert EvidenceItem(file_size=1024).file_size_display == "1.0 KB"

    def test_megabytes(self):
        assert EvidenceItem(file_size=2 * 1024 * 1024).file_size_display == "2.0 MB"

    def test_exact_megabyte_boundary(self):
        assert EvidenceItem(file_size=1024 * 1024).file_size_display == "1.0 MB"


@pytest.mark.django_db
class TestEvidenceListDefaults:
    def test_default_values(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="测试", list_type=ListType.LIST_1)
        assert el.export_version == 1
        assert el.merge_status == MergeStatus.PENDING.value
        assert el.total_pages == 0
        assert el.merge_progress == 0
        assert el.merge_current == 0
        assert el.merge_total == 0
        assert el.merge_error == ""
        assert el.merge_message == ""


@pytest.mark.django_db
class TestEvidenceItemDefaults:
    def test_default_values(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(evidence_list=el, order=1, name="证物", purpose="证明")
        assert item.file_size == 0
        assert item.page_count == 0
        assert item.page_start is None
        assert item.page_end is None
        assert item.file_name == ""
        assert item.ai_analysis == {}
