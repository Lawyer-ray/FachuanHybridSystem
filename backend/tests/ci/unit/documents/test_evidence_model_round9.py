"""documents.models.evidence — round9 tests for remaining uncovered branches.

Uses the apps.evidence.models.EvidenceList/EvidenceItem (the working model
registration) to test all model properties and methods with @pytest.mark.django_db.
Covers remaining gaps in end_page, page_range_display, order_range_display,
EvidenceItem.file_size_display, EvidenceItem.page_range_display, __str__.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.evidence.models import EvidenceItem, EvidenceList, ListType, MergeStatus
from apps.testing.factories import CaseFactory


# ══════════════════════════════════════════════════════════════════════════════
# MergeStatus / ListType — complete value coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestMergeStatusComplete:
    def test_all_members(self):
        members = {
            MergeStatus.PENDING: "pending",
            MergeStatus.PROCESSING: "processing",
            MergeStatus.COMPLETED: "completed",
            MergeStatus.FAILED: "failed",
        }
        for member, expected_value in members.items():
            assert member.value == expected_value

    def test_choices_tuples(self):
        choices = MergeStatus.choices
        values = [c[0] for c in choices]
        assert "pending" in values
        assert "processing" in values
        assert "completed" in values
        assert "failed" in values


class TestListTypeComplete:
    def test_all_six_values(self):
        expected = [f"list_{i}" for i in range(1, 7)]
        actual = [lt.value for lt in ListType]
        assert actual == expected

    def test_labels(self):
        labels = {lt.value: lt.label for lt in ListType}
        assert labels["list_1"] == "证据清单一"
        assert labels["list_6"] == "证据清单六"


# ══════════════════════════════════════════════════════════════════════════════
# LIST_TYPE_ORDER / LIST_TYPE_PREVIOUS — module-level dicts
# ══════════════════════════════════════════════════════════════════════════════


class TestListTypeOrderModule:
    def test_all_values(self):
        from apps.evidence.models.evidence import LIST_TYPE_ORDER

        for i in range(1, 7):
            assert LIST_TYPE_ORDER[ListType(f"list_{i}")] == i


class TestListTypePreviousModule:
    def test_chain(self):
        from apps.evidence.models.evidence import LIST_TYPE_PREVIOUS

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1
        assert LIST_TYPE_PREVIOUS[ListType.LIST_6] == ListType.LIST_5


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — __str__
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListStr:
    def test_str_with_title(self):
        case = CaseFactory(name="张三诉李四合同纠纷")
        el = EvidenceList.objects.create(
            case=case, title="证据清单一", list_type=ListType.LIST_1
        )
        assert str(el) == "张三诉李四合同纠纷 - 证据清单一"

    def test_str_empty_title(self):
        case = CaseFactory(name="空标题案")
        el = EvidenceList.objects.create(
            case=case, title="", list_type=ListType.LIST_1
        )
        result = str(el)
        assert "空标题案" in result
        assert " - " in result

    def test_str_long_title(self):
        case = CaseFactory(name="案")
        long_title = "A" * 100
        el = EvidenceList.objects.create(
            case=case, title=long_title, list_type=ListType.LIST_1
        )
        assert long_title in str(el)


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — end_page property
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListEndPage:
    def test_end_page_zero_total(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 0
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 5
            assert el.end_page == 5  # start_page when total_pages==0

    def test_end_page_nonzero_total(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 10
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 3
            assert el.end_page == 12  # 3 + 10 - 1

    def test_end_page_one_page(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 1
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 1
            assert el.end_page == 1


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — page_range_display property
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListPageRangeDisplay:
    def test_empty_when_zero_total(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 0
        assert el.page_range_display == ""

    def test_range_display(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 5
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 10
            assert el.page_range_display == "10-14"

    def test_single_page_display(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.total_pages = 1
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_page.return_value = 7
            assert el.page_range_display == "7-7"


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — order_range_display property
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListOrderRangeDisplay:
    def test_zero_items_returns_dash(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        assert el.order_range_display == "-"

    def test_single_item(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        EvidenceItem.objects.create(evidence_list=el, order=1, name="合同", purpose="证明")
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 1
            assert el.order_range_display == "1"

    def test_multiple_items(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        for i in range(1, 6):
            EvidenceItem.objects.create(evidence_list=el, order=i, name=f"证据{i}", purpose="证明")
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 3
            assert el.order_range_display == "3-7"

    def test_uses_item_count_attr_if_set(self):
        """When item_count attribute is set, skips the ORM query."""
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        el.item_count = 3  # type: ignore[attr-defined]
        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            mock_svc.return_value.calculate_start_order.return_value = 5
            assert el.order_range_display == "5-7"


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — start_order / start_page delegation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListDelegation:
    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_order(self, mock_svc):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        mock_svc.return_value.calculate_start_order.return_value = 42
        assert el.start_order == 42

    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_page(self, mock_svc):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        mock_svc.return_value.calculate_start_page.return_value = 99
        assert el.start_page == 99


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — Meta unique constraint
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListMeta:
    def test_unique_case_list_type(self):
        case = CaseFactory()
        EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1)
        with pytest.raises(Exception):
            EvidenceList.objects.create(case=case, title="二", list_type=ListType.LIST_1)

    def test_different_list_type_ok(self):
        case = CaseFactory()
        EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1)
        el2 = EvidenceList.objects.create(case=case, title="二", list_type=ListType.LIST_2)
        assert el2.pk is not None


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceList — defaults
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceListDefaults:
    def test_default_field_values(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        assert el.export_version == 1
        assert el.merge_status == MergeStatus.PENDING.value
        assert el.total_pages == 0
        assert el.merge_progress == 0
        assert el.merge_current == 0
        assert el.merge_total == 0
        assert el.merge_error == ""
        assert el.merge_message == ""
        assert el.order == 1

    def test_list_type_default(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t")
        assert el.list_type == ListType.LIST_1.value


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceItem — __str__
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceItemStr:
    def test_str(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(
            evidence_list=el, order=5, name="转账凭证", purpose="证明"
        )
        assert str(item) == "5. 转账凭证"

    def test_str_zero_order(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(
            evidence_list=el, order=0, name="无编号证据", purpose="证明"
        )
        assert str(item) == "0. 无编号证据"

    def test_str_high_order(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(
            evidence_list=el, order=999, name="最后证据", purpose="证明"
        )
        assert str(item) == "999. 最后证据"


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceItem — page_range_display
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceItemPageRangeDisplay:
    def test_both_none(self):
        item = EvidenceItem(page_start=None, page_end=None)
        assert item.page_range_display == "-"

    def test_start_none_end_set(self):
        item = EvidenceItem(page_start=None, page_end=5)
        assert item.page_range_display == "-"

    def test_start_set_end_none(self):
        item = EvidenceItem(page_start=3, page_end=None)
        assert item.page_range_display == "-"

    def test_same_page(self):
        item = EvidenceItem(page_start=7, page_end=7)
        assert item.page_range_display == "7"

    def test_range(self):
        item = EvidenceItem(page_start=2, page_end=10)
        assert item.page_range_display == "2-10"


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceItem — file_size_display
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceItemFileSizeDisplay:
    def test_zero(self):
        assert EvidenceItem(file_size=0).file_size_display == "-"

    def test_one_byte(self):
        assert EvidenceItem(file_size=1).file_size_display == "1 B"

    def test_exactly_1023_bytes(self):
        assert EvidenceItem(file_size=1023).file_size_display == "1023 B"

    def test_exactly_1024_bytes(self):
        assert EvidenceItem(file_size=1024).file_size_display == "1.0 KB"

    def test_1500_bytes(self):
        assert EvidenceItem(file_size=1500).file_size_display == "1.5 KB"

    def test_exactly_1MB(self):
        assert EvidenceItem(file_size=1024 * 1024).file_size_display == "1.0 MB"

    def test_2point5MB(self):
        size = int(2.5 * 1024 * 1024)
        assert EvidenceItem(file_size=size).file_size_display == "2.5 MB"

    def test_large_file(self):
        size = 100 * 1024 * 1024
        assert EvidenceItem(file_size=size).file_size_display == "100.0 MB"


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceItem — defaults
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceItemDefaults:
    def test_default_values(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(evidence_list=el, order=1, name="证物", purpose="证明")
        assert item.file_size == 0
        assert item.page_count == 0
        assert item.page_start is None
        assert item.page_end is None
        assert item.file_name == ""
        assert item.ai_analysis == {}

    def test_order_default(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        item = EvidenceItem(evidence_list=el, name="证物", purpose="证明")
        assert item.order == 0


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceItem — ordering
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEvidenceItemOrdering:
    def test_ordering_by_order(self):
        case = CaseFactory()
        el = EvidenceList.objects.create(case=case, title="t", list_type=ListType.LIST_1)
        EvidenceItem.objects.create(evidence_list=el, order=3, name="C", purpose="p")
        EvidenceItem.objects.create(evidence_list=el, order=1, name="A", purpose="p")
        EvidenceItem.objects.create(evidence_list=el, order=2, name="B", purpose="p")
        items = list(el.items.all())
        assert [i.name for i in items] == ["A", "B", "C"]


# ══════════════════════════════════════════════════════════════════════════════
# _get_evidence_service / _get_evidence_storage — factory functions
# ══════════════════════════════════════════════════════════════════════════════


class TestFactoryFunctions:
    def test_get_evidence_service_returns_service(self):
        from apps.evidence.models.evidence import _get_evidence_service
        svc = _get_evidence_service()
        assert svc is not None
        assert hasattr(svc, "calculate_start_order")
        assert hasattr(svc, "calculate_start_page")

    def test_get_evidence_storage_returns_storage(self):
        from apps.evidence.models.evidence import _get_evidence_storage
        storage = _get_evidence_storage()
        assert storage is not None
