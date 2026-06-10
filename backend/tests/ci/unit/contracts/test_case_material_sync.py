"""Tests for case_material_sync module."""

import pytest
from unittest.mock import MagicMock, patch

from apps.contracts.services.archive.checklist.case_material_sync import (
    _apply_initial_order_for_synced,
    upload_material_to_archive_item,
)


class TestApplyInitialOrderForSynced:
    def test_empty_synced(self):
        # Should not raise
        _apply_initial_order_for_synced([])

    def test_single_item_no_reorder(self, db):
        # Single item should not need reordering
        _apply_initial_order_for_synced([{"material_id": 99999, "archive_item_code": "code"}])


class TestUploadMaterialToArchiveItem:
    def test_invalid_code_raises(self, db):
        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1

        with pytest.raises(ValueError, match="无效的归档清单编号"):
            upload_material_to_archive_item(contract, "INVALID_CODE", MagicMock())

    @patch("apps.core.services.storage_service.save_uploaded_file")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    def test_valid_upload(self, mock_category, mock_model, mock_save, db):
        from apps.contracts.services.archive.checklist.case_material_sync import upload_material_to_archive_item

        mock_category.return_value = "litigation"

        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1

        mock_save.return_value = ("contracts/finalized/1/test.pdf", "test.pdf")
        mock_material = MagicMock()
        mock_material.id = 1
        mock_model.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_model.objects.create.return_value = mock_material

        uploaded_file = MagicMock()
        # Use a code that exists in the real ARCHIVE_CHECKLIST for 'litigation'
        # Let's check what codes exist
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST
        litigation_items = ARCHIVE_CHECKLIST.get("litigation", [])
        if not litigation_items:
            pytest.skip("No litigation checklist items found")
        test_code = litigation_items[0]["code"]

        result = upload_material_to_archive_item(contract, test_code, uploaded_file)
        assert result.id == 1


class TestGetCaseMaterialMatchMap:
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.CASE_MATERIAL_KEYWORD_MAPPING")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.ARCHIVE_CHECKLIST")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    def test_basic_match_map(self, mock_fm, mock_checklist, mock_kw, mock_category, db):
        from apps.contracts.services.archive.checklist.case_material_sync import get_case_material_match_map

        mock_category.return_value = "litigation"
        mock_kw.get.return_value = {}
        mock_checklist.get.return_value = []
        mock_fm.objects.filter.return_value.values_list.return_value = []

        contract = MagicMock()
        contract.case_type = "civil"
        contract.cases.all.return_value.only.return_value = []

        result = get_case_material_match_map(contract)
        assert "archive_category" in result
        assert "cases" in result
        assert "summary" in result


class TestResetAndResync:
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.ARCHIVE_CHECKLIST")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    def test_no_target_codes(self, mock_fm, mock_checklist, mock_category, db):
        from apps.contracts.services.archive.checklist.case_material_sync import reset_and_resync_case_materials

        mock_category.return_value = "litigation"
        mock_checklist.get.return_value = []

        contract = MagicMock()
        contract.case_type = "civil"

        result = reset_and_resync_case_materials(contract)
        assert result["deleted_count"] == 0
