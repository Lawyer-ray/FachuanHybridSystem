"""PDF utils tests with mocked fitz."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.generation.pdf_utils import (
    A4_H,
    A4_W,
    TOLERANCE,
    add_page_numbers,
    merge_materials_to_single_pdf,
    scale_pages_to_a4,
)


class TestConstants:
    def test_a4_dimensions(self):
        assert A4_W == 595.0
        assert A4_H == 842.0
        assert TOLERANCE == 1.0


class TestScalePagesToA4:
    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_no_pdf_materials(self, mock_material_model):
        mock_material_model.objects.filter.return_value.order_by.return_value = []
        contract = MagicMock()
        result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert result["scaled_count"] == 0

    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_file_not_exists(self, mock_material_model):
        material = MagicMock()
        material.file_path = "/nonexistent/file.pdf"
        material.original_filename = "test.pdf"
        mock_material_model.objects.filter.return_value.order_by.return_value = [material]

        with patch("apps.contracts.services.archive.generation.pdf_utils.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.is_absolute.return_value = True
            mock_path_instance.exists.return_value = False
            mock_path.return_value = mock_path_instance

            contract = MagicMock()
            result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert len(result["errors"]) > 0


class TestAddPageNumbers:
    def test_add_page_numbers(self):
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.new_page(width=595, height=842)
        add_page_numbers(doc, start_page=1)
        assert len(doc) == 2
        doc.close()


class TestMergeMaterialsToSinglePdf:
    def test_merge_empty_materials(self):
        result = merge_materials_to_single_pdf([])
        assert result["success"] is False

    def test_merge_with_nonexistent_files(self):
        material = MagicMock()
        material.file_path = "/nonexistent/test.pdf"
        material.original_filename = "test.pdf"

        with patch("apps.contracts.services.archive.generation.pdf_utils.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.is_absolute.return_value = True
            mock_path_instance.exists.return_value = False
            mock_path_instance.suffix = ".pdf"
            mock_path.return_value = mock_path_instance

            result = merge_materials_to_single_pdf([material])
        # No files could be opened, so merged_doc is empty
        assert result["success"] is False
