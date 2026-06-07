"""documents/admin/ 单元测试（evidence mixins + placeholder_admin）。"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.documents.admin.evidence.mixins.views import (
    EvidenceListAdminServiceMixin,
    EvidenceListAdminViewsMixin,
)
from apps.documents.admin.evidence.mixins.save import EvidenceListAdminSaveMixin
from apps.documents.admin.placeholder_admin import (
    PlaceholderAdmin,
    PlaceholderUsageFilter,
)


class TestEvidenceListAdminViewsMixinDisplayMethods:
    def _make_mixin(self):
        return EvidenceListAdminViewsMixin()

    def test_total_pages_display_zero(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.total_pages = 0
        assert mixin.total_pages_display(obj) == ""

    def test_total_pages_display_nonzero(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.total_pages = 5
        assert mixin.total_pages_display(obj) == 5

    def test_case_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.case.name = "测试案件"
        assert mixin.case_display(obj) == "测试案件"

    def test_item_count_display_with_annotation(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.item_count = 3
        assert mixin.item_count_display(obj) == 3

    def test_item_count_display_without_annotation(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock(spec=[])
        obj.items = MagicMock()
        obj.items.count.return_value = 5
        result = mixin.item_count_display(obj)
        assert result == 5

    def test_page_range_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.page_range_display = "1-10"
        assert mixin.page_range_display(obj) == "1-10"

    def test_order_range_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.order_range_display = "1-5"
        assert mixin.order_range_display(obj) == "1-5"

    def test_has_merged_pdf_processing_status(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.merge_status = "processing"
        obj.merge_progress = 50
        obj.merge_current = 3
        obj.merge_total = 6
        obj.merge_message = "处理中"
        obj.merged_pdf = None
        result = mixin.has_merged_pdf_display(obj)
        result_str = str(result)
        assert "50%" in result_str or "合并中" in result_str

    def test_has_merged_pdf_failed_status(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.merge_status = "failed"
        obj.merge_error = "转换失败"
        obj.merged_pdf = None
        result = mixin.has_merged_pdf_display(obj)
        result_str = str(result)
        assert "失败" in result_str

    def test_has_merged_pdf_completed_with_pdf(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.merge_status = "completed"
        obj.merged_pdf = MagicMock()
        result = mixin.has_merged_pdf_display(obj)
        assert "已合并" in str(result)

    def test_has_merged_pdf_pending_no_pdf(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.merge_status = "pending"
        obj.merged_pdf = None
        result = mixin.has_merged_pdf_display(obj)
        assert "未合并" in str(result)


class TestEvidenceListAdminSaveMixinPrepareEvidenceItem:
    def test_new_item_sets_order(self) -> None:
        obj = MagicMock()
        obj.pk = None
        obj.file = None
        EvidenceListAdminSaveMixin._prepare_evidence_item(obj, 5, [])
        assert obj.order == 6

    def test_existing_item_order_unchanged(self) -> None:
        obj = MagicMock()
        obj.pk = 1
        obj.order = 3
        obj.file = None
        EvidenceListAdminSaveMixin._prepare_evidence_item(obj, 5, [])
        assert obj.order == 3

    def test_pdf_file_added_to_page_count_list(self) -> None:
        obj = MagicMock()
        obj.pk = 1
        obj.file.name = "test.pdf"
        obj.file.size = 1024
        items_list: list = []
        EvidenceListAdminSaveMixin._prepare_evidence_item(obj, 5, items_list)
        assert len(items_list) == 1
        assert obj.file_name == "test.pdf"
        assert obj.file_size == 1024
        assert obj.page_count == 1

    def test_non_pdf_not_added_to_page_count_list(self) -> None:
        obj = MagicMock()
        obj.pk = 1
        obj.file.name = "test.jpg"
        obj.file.size = 500
        items_list: list = []
        EvidenceListAdminSaveMixin._prepare_evidence_item(obj, 5, items_list)
        assert len(items_list) == 0

    def test_no_file_no_error(self) -> None:
        obj = MagicMock()
        obj.pk = 1  # existing item
        obj.file = None
        items_list: list = []
        # Should not raise even when file is None
        EvidenceListAdminSaveMixin._prepare_evidence_item(obj, 5, items_list)
        assert len(items_list) == 0


class TestEvidenceListAdminSaveMixinRecalculateListPages:
    def test_calculates_total(self) -> None:
        evidence_list = MagicMock()
        item1 = MagicMock()
        item1.page_count = 5
        item2 = MagicMock()
        item2.page_count = 3
        evidence_list.items.all.return_value = [item1, item2]
        evidence_list.total_pages = 0

        mixin = EvidenceListAdminSaveMixin()
        mixin._recalculate_list_pages(evidence_list)
        assert evidence_list.total_pages == 8

    def test_no_change_skips_save(self) -> None:
        evidence_list = MagicMock()
        item = MagicMock()
        item.page_count = 5
        evidence_list.items.all.return_value = [item]
        evidence_list.total_pages = 5

        mixin = EvidenceListAdminSaveMixin()
        mixin._recalculate_list_pages(evidence_list)
        evidence_list.save.assert_not_called()


class TestPlaceholderUsageFilter:
    def test_lookups(self) -> None:
        f = PlaceholderUsageFilter(None, {}, None, None)
        lookups = f.lookups(None, None)
        lookup_keys = [l[0] for l in lookups]
        assert "contract" in lookup_keys
        assert "case" in lookup_keys
        assert "both" in lookup_keys
        assert "unused" in lookup_keys

    def test_queryset_no_value(self) -> None:
        f = PlaceholderUsageFilter(None, {}, None, None)
        qs = MagicMock()
        result = f.queryset(None, qs)
        assert result is qs


class TestPlaceholderAdmin:
    def test_has_add_permission_false(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        assert admin.has_add_permission(None) is False

    def test_get_readonly_fields_editing(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        obj = MagicMock()
        result = admin.get_readonly_fields(None, obj)
        assert "key" in result

    def test_get_readonly_fields_creating(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        result = admin.get_readonly_fields(None, None)
        assert result == ()


class TestPlaceholderAdminDisplayMethods:
    def test_usage_display_with_contract(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        admin._usage_map_for_changelist = {"key1": {"contract"}}
        obj = MagicMock()
        obj.key = "key1"
        result = admin.usage_display(obj)
        assert "合同文件" in result

    def test_usage_display_with_case(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        admin._usage_map_for_changelist = {"key1": {"case"}}
        obj = MagicMock()
        obj.key = "key1"
        result = admin.usage_display(obj)
        assert "案件文件" in result

    def test_usage_display_empty(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        admin._usage_map_for_changelist = {"key1": set()}
        obj = MagicMock()
        obj.key = "key1"
        result = admin.usage_display(obj)
        assert "-" in str(result)

    def test_example_value_display_short(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        obj = MagicMock()
        obj.example_value = "短值"
        result = admin.example_value_display(obj)
        assert "短值" in result

    def test_example_value_display_long_truncated(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        obj = MagicMock()
        obj.example_value = "A" * 100
        result = admin.example_value_display(obj)
        assert "..." in str(result)

    def test_example_value_display_empty(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        obj = MagicMock()
        obj.example_value = ""
        result = admin.example_value_display(obj)
        assert "-" in str(result)

    def test_code_service_display_with_definition(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        definition = MagicMock()
        definition.source = "TestCaseService"
        admin._cached_code_placeholder_catalog = {"key1": definition}
        obj = MagicMock()
        obj.key = "key1"
        assert admin.code_service_display(obj) == "TestCaseService"

    def test_code_service_display_no_definition(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        admin._cached_code_placeholder_catalog = {}
        obj = MagicMock()
        obj.key = "unknown"
        assert admin.code_service_display(obj) == ""

    def test_code_category_display(self) -> None:
        admin = PlaceholderAdmin.__new__(PlaceholderAdmin)
        definition = MagicMock()
        definition.category = "合同"
        admin._cached_code_placeholder_catalog = {"key1": definition}
        obj = MagicMock()
        obj.key = "key1"
        assert admin.code_category_display(obj) == "合同"
