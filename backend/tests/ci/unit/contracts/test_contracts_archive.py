"""contracts/services/archive/ 单元测试（folder_builder + pdf_utils + case_material_sync）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestPdfUtilsConstants:
    def test_a4_dimensions(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import A4_W, A4_H
        assert A4_W == 595.0
        assert A4_H == 842.0

    def test_tolerance(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import TOLERANCE
        assert TOLERANCE == 1.0


class TestFolderBuilderConstants:
    def test_archive_catalog_codes(self) -> None:
        from apps.contracts.services.archive.generation.folder_builder import _ARCHIVE_CATALOG_CODES
        assert _ARCHIVE_CATALOG_CODES["non_litigation"] == "nl_3"
        assert _ARCHIVE_CATALOG_CODES["litigation"] == "lt_3"
        assert _ARCHIVE_CATALOG_CODES["criminal"] == "cr_3"

    def test_is_dict(self) -> None:
        from apps.contracts.services.archive.generation.folder_builder import _ARCHIVE_CATALOG_CODES
        assert isinstance(_ARCHIVE_CATALOG_CODES, dict)


class TestGenerateArchiveFolder:
    def test_no_folder_path_returns_error(self) -> None:
        from apps.contracts.services.archive.generation.folder_builder import generate_archive_folder
        contract = MagicMock()
        binding = MagicMock()
        binding.folder_path = ""
        contract.folder_binding = binding
        result = generate_archive_folder(contract)
        assert result["success"] is False
        assert "未绑定" in result["error"]

    def test_none_folder_path_returns_error(self) -> None:
        from apps.contracts.services.archive.generation.folder_builder import generate_archive_folder
        contract = MagicMock()
        binding = MagicMock()
        binding.folder_path = None
        contract.folder_binding = binding
        result = generate_archive_folder(contract)
        assert result["success"] is False


class TestCaseMaterialSyncModule:
    def test_functions_exist(self) -> None:
        from apps.contracts.services.archive.checklist.case_material_sync import (
            get_case_material_match_map,
            sync_case_materials_to_archive,
            reset_and_resync_case_materials,
            upload_material_to_archive_item,
        )
        assert callable(get_case_material_match_map)
        assert callable(sync_case_materials_to_archive)
        assert callable(reset_and_resync_case_materials)
        assert callable(upload_material_to_archive_item)


class TestApplyInitialOrderForSynced:
    def test_empty_synced_noop(self) -> None:
        from apps.contracts.services.archive.checklist.case_material_sync import _apply_initial_order_for_synced
        _apply_initial_order_for_synced([])


class TestCopyCaseMaterialToFinalized:
    def test_no_attachment_returns_none(self) -> None:
        from apps.contracts.services.archive.checklist.case_material_sync import _copy_case_material_to_finalized
        contract = MagicMock()
        cm = MagicMock()
        cm.source_attachment = None
        result = _copy_case_material_to_finalized(contract, cm, "code")
        assert result is None

    def test_no_file_path_returns_none(self) -> None:
        from apps.contracts.services.archive.checklist.case_material_sync import _copy_case_material_to_finalized
        contract = MagicMock()
        cm = MagicMock()
        cm.source_attachment.file.name = ""
        result = _copy_case_material_to_finalized(contract, cm, "code")
        assert result is None


class TestCompileCaseMaterialsPdf:
    def test_function_exists(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import compile_case_materials_pdf
        assert callable(compile_case_materials_pdf)


class TestScalePagesToA4:
    def test_function_exists(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4
        assert callable(scale_pages_to_a4)

    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_no_materials_returns_success(self, MockMat: MagicMock) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4
        MockMat.objects.filter.return_value.order_by.return_value = []
        contract = MagicMock()
        result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert result["scaled_count"] == 0
        assert result["skipped_count"] == 0


class TestMergeMaterialsToSinglePdf:
    def test_function_exists(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import merge_materials_to_single_pdf
        assert callable(merge_materials_to_single_pdf)
