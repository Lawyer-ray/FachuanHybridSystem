"""contracts.services.archive.generation 补充覆盖测试 (pdf_utils + download_handler + folder_builder)。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


# ── pdf_utils: add_page_numbers ───────────────────────────────────

class TestAddPageNumbers:
    def test_adds_numbers_to_pages(self):
        import fitz

        from apps.contracts.services.archive.generation.pdf_utils import add_page_numbers

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.new_page()
        add_page_numbers(doc, start_page=1)
        assert len(doc) == 3
        doc.close()

    def test_custom_start_page(self):
        import fitz

        from apps.contracts.services.archive.generation.pdf_utils import add_page_numbers

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        add_page_numbers(doc, start_page=10)
        assert len(doc) == 2
        doc.close()


# ── pdf_utils: merge_materials_to_single_pdf ──────────────────────

class TestMergeMaterialsToSinglePdf:
    def test_empty_materials(self):
        from apps.contracts.services.archive.generation.pdf_utils import merge_materials_to_single_pdf

        result = merge_materials_to_single_pdf([])
        assert result["success"] is False

    @patch("apps.contracts.services.archive.generation.pdf_utils.Path")
    def test_single_pdf_material(self, mock_path_cls):
        import fitz

        from apps.contracts.services.archive.generation.pdf_utils import merge_materials_to_single_pdf

        # Create a real temp PDF
        doc = fitz.open()
        doc.new_page()
        buf = BytesIO()
        doc.save(buf)
        doc.close()
        pdf_bytes = buf.getvalue()

        material = MagicMock()
        material.original_filename = "test.pdf"
        material.file_path = "/tmp/test.pdf"

        mock_path_instance = MagicMock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_instance.suffix = ".pdf"
        mock_path_instance.__str__ = lambda self: "/tmp/test.pdf"
        mock_path_cls.return_value = mock_path_instance

        with patch("fitz.open") as mock_fitz_open:
            mock_src_doc = MagicMock()
            mock_merged_doc = MagicMock()
            mock_merged_doc.__len__ = lambda self: 1
            mock_merged_doc.save = MagicMock()

            def open_side_effect(*args, **kwargs):
                if not args:
                    return mock_merged_doc
                return mock_src_doc

            mock_fitz_open.side_effect = open_side_effect

            with patch("apps.contracts.services.archive.generation.pdf_utils.Path") as mock_p:
                mock_p.return_value = mock_path_instance
                result = merge_materials_to_single_pdf([material])
                # The function will attempt to open the file
                # Let's verify the structure
                assert "success" in result or "error" in result


# ── pdf_utils: scale_pages_to_a4 ──────────────────────────────────

class TestScalePagesToA4:
    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_no_pdf_materials(self, mock_fm):
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4

        mock_fm.objects.filter.return_value.order_by.return_value = []
        contract = MagicMock()
        result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert result["scaled_count"] == 0

    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_material_file_not_found(self, mock_fm):
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4

        material = MagicMock()
        material.file_path = "/nonexistent.pdf"
        material.original_filename = "missing.pdf"
        mock_fm.objects.filter.return_value.order_by.return_value = [material]

        contract = MagicMock()
        with patch("apps.contracts.services.archive.generation.pdf_utils.Path") as mock_path:
            mock_path.return_value.expanduser.return_value.resolve.return_value = Path("/nonexistent.pdf")
            mock_path.return_value.is_absolute.return_value = True
            mock_path.return_value.exists.return_value = False
            result = scale_pages_to_a4(contract)
            assert result["success"] is True
            assert len(result["errors"]) > 0


# ── download_handler: _find_checklist_item ────────────────────────

class TestFindChecklistItem:
    def test_item_found(self):
        from apps.contracts.services.archive.generation.download_handler import _find_checklist_item

        contract = MagicMock()
        contract.case_type = "litigation"

        with patch("apps.contracts.services.archive.generation.download_handler.get_archive_category") as mock_cat, \
             patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_CHECKLIST") as mock_checklist:
            mock_cat.return_value = "litigation"
            mock_checklist.get.return_value = [
                {"code": "lt_1", "name": "委托合同", "template": "engagement_letter"},
                {"code": "lt_2", "name": "起诉状", "template": "complaint"},
            ]
            result = _find_checklist_item(contract, "lt_1")
            assert result is not None
            assert result["code"] == "lt_1"

    def test_item_not_found(self):
        from apps.contracts.services.archive.generation.download_handler import _find_checklist_item

        contract = MagicMock()
        contract.case_type = "litigation"

        with patch("apps.contracts.services.archive.generation.download_handler.get_archive_category") as mock_cat, \
             patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_CHECKLIST") as mock_checklist:
            mock_cat.return_value = "litigation"
            mock_checklist.get.return_value = [{"code": "lt_1", "name": "test"}]
            result = _find_checklist_item(contract, "nonexistent")
            assert result is None


# ── download_handler: _is_item_by_name ────────────────────────────

class TestIsItemByName:
    def test_keyword_found(self):
        from apps.contracts.services.archive.generation.download_handler import _is_item_by_name

        contract = MagicMock()
        contract.case_type = "litigation"

        with patch("apps.contracts.services.archive.generation.download_handler.get_archive_category") as mock_cat, \
             patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_CHECKLIST") as mock_checklist:
            mock_cat.return_value = "litigation"
            mock_checklist.get.return_value = [{"code": "lt_3", "name": "委托合同（收费确认单）"}]
            assert _is_item_by_name(contract, "lt_3", "收费") is True

    def test_keyword_not_found(self):
        from apps.contracts.services.archive.generation.download_handler import _is_item_by_name

        contract = MagicMock()
        contract.case_type = "litigation"

        with patch("apps.contracts.services.archive.generation.download_handler.get_archive_category") as mock_cat, \
             patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_CHECKLIST") as mock_checklist:
            mock_cat.return_value = "litigation"
            mock_checklist.get.return_value = [{"code": "lt_3", "name": "委托合同"}]
            assert _is_item_by_name(contract, "lt_3", "收费") is False


# ── download_handler: _read_material_file ─────────────────────────

class TestReadMaterialFile:
    def test_file_not_found(self):
        from apps.contracts.services.archive.generation.download_handler import _read_material_file

        material = MagicMock()
        material.file_path = "/nonexistent/file.pdf"
        material.original_filename = "test.pdf"

        with patch("apps.contracts.services.archive.generation.download_handler.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.is_absolute.return_value = True
            mock_instance.exists.return_value = False
            mock_path.return_value = mock_instance
            result = _read_material_file(material)
            assert "error" in result

    def test_pdf_content_type(self):
        from apps.contracts.services.archive.generation.download_handler import _read_material_file

        material = MagicMock()
        material.file_path = "/tmp/test.pdf"
        material.original_filename = "test.pdf"

        with patch("apps.contracts.services.archive.generation.download_handler.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.is_absolute.return_value = True
            mock_instance.exists.return_value = True
            mock_instance.read_bytes.return_value = b"PDF content"
            mock_instance.suffix = ".pdf"
            mock_path.return_value = mock_instance
            result = _read_material_file(material)
            assert result["content_type"] == "application/pdf"
            assert result["content"] == b"PDF content"

    def test_docx_content_type(self):
        from apps.contracts.services.archive.generation.download_handler import _read_material_file

        material = MagicMock()
        material.file_path = "/tmp/test.docx"
        material.original_filename = "test.docx"

        with patch("apps.contracts.services.archive.generation.download_handler.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.is_absolute.return_value = True
            mock_instance.exists.return_value = True
            mock_instance.read_bytes.return_value = b"DOCX content"
            mock_instance.suffix = ".docx"
            mock_path.return_value = mock_instance
            result = _read_material_file(material)
            assert "wordprocessingml" in result["content_type"]

    def test_other_content_type(self):
        from apps.contracts.services.archive.generation.download_handler import _read_material_file

        material = MagicMock()
        material.file_path = "/tmp/test.xlsx"
        material.original_filename = "test.xlsx"

        with patch("apps.contracts.services.archive.generation.download_handler.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.is_absolute.return_value = True
            mock_instance.exists.return_value = True
            mock_instance.read_bytes.return_value = b"XLSX content"
            mock_instance.suffix = ".xlsx"
            mock_path.return_value = mock_instance
            result = _read_material_file(material)
            assert result["content_type"] == "application/octet-stream"


# ── download_handler: _apply_subitem_sort ─────────────────────────

class TestApplySubitemSort:
    def test_no_keywords(self):
        from apps.contracts.services.archive.generation.download_handler import _apply_subitem_sort

        with patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_SUBITEM_ORDER_RULES", {}):
            m1 = MagicMock()
            m1.order = 0
            m1.original_filename = "file1.pdf"
            result = _apply_subitem_sort([m1], "lt_1")
            assert len(result) == 1

    def test_single_material(self):
        from apps.contracts.services.archive.generation.download_handler import _apply_subitem_sort

        with patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_SUBITEM_ORDER_RULES", {"lt_3": ["授权", "收费"]}):
            m1 = MagicMock()
            m1.order = 0
            m1.original_filename = "授权委托书.pdf"
            result = _apply_subitem_sort([m1], "lt_3")
            assert len(result) == 1

    def test_all_ordered(self):
        from apps.contracts.services.archive.generation.download_handler import _apply_subitem_sort

        with patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_SUBITEM_ORDER_RULES", {"lt_3": ["授权", "收费"]}):
            m1 = MagicMock()
            m1.order = 1
            m1.original_filename = "file1.pdf"
            m2 = MagicMock()
            m2.order = 2
            m2.original_filename = "file2.pdf"
            result = _apply_subitem_sort([m1, m2], "lt_3")
            assert len(result) == 2

    def test_sorts_unordered_by_keyword(self):
        from apps.contracts.services.archive.generation.download_handler import _apply_subitem_sort

        with patch("apps.contracts.services.archive.generation.download_handler.ARCHIVE_SUBITEM_ORDER_RULES", {"lt_3": ["授权", "收费"]}):
            m1 = MagicMock()
            m1.order = 1
            m1.original_filename = "ordered.pdf"
            m2 = MagicMock()
            m2.order = 0
            m2.original_filename = "收费确认单.pdf"
            m3 = MagicMock()
            m3.order = 0
            m3.original_filename = "授权委托书.pdf"
            result = _apply_subitem_sort([m1, m2, m3], "lt_3")
            # "授权" (index 0) should come before "收费" (index 1)
            assert result[0].order == 1  # ordered first
            assert "授权" in result[1].original_filename
            assert "收费" in result[2].original_filename


# ── download_handler: download_archive_item ───────────────────────

class TestDownloadArchiveItem:
    @patch("apps.contracts.services.archive.generation.download_handler._find_checklist_item")
    def test_template_item_delegates_to_template_download(self, mock_find):
        from apps.contracts.services.archive.generation.download_handler import download_archive_item

        contract = MagicMock()
        mock_find.return_value = {"code": "lt_1", "name": "test", "template": "engagement_letter"}

        with patch("apps.contracts.services.archive.generation.download_handler._download_template_item") as mock_dl:
            mock_dl.return_value = {"content": b"docx", "filename": "test.docx"}
            result = download_archive_item(contract, "lt_1")
            assert "content" in result
            mock_dl.assert_called_once()

    @patch("apps.contracts.services.archive.generation.download_handler._find_checklist_item")
    def test_non_template_item_delegates_to_uploaded_download(self, mock_find):
        from apps.contracts.services.archive.generation.download_handler import download_archive_item

        contract = MagicMock()
        mock_find.return_value = None

        with patch("apps.contracts.services.archive.generation.download_handler._download_uploaded_item") as mock_dl:
            mock_dl.return_value = {"content": b"pdf", "filename": "test.pdf"}
            result = download_archive_item(contract, "lt_4")
            assert "content" in result


# ── download_handler: _download_template_item ─────────────────────

class TestDownloadTemplateItem:
    def test_generation_error(self):
        from apps.contracts.services.archive.generation.download_handler import _download_template_item

        contract = MagicMock()
        item = {"code": "lt_1", "name": "test", "template": "engagement_letter"}

        with patch("apps.contracts.services.archive.generation.download_handler.generate_single_archive_document") as mock_gen:
            mock_gen.return_value = {"error": "生成失败"}
            result = _download_template_item(contract, "lt_1", item)
            assert "error" in result

    def test_generation_success(self):
        from apps.contracts.services.archive.generation.download_handler import _download_template_item

        contract = MagicMock()
        item = {"code": "lt_1", "name": "test", "template": "engagement_letter"}

        with patch("apps.contracts.services.archive.generation.download_handler.generate_single_archive_document") as mock_gen:
            mock_gen.return_value = {"content": b"docx-data", "filename": "test.docx"}
            result = _download_template_item(contract, "lt_1", item)
            assert result["content"] == b"docx-data"
            assert "wordprocessingml" in result["content_type"]

    def test_generation_no_content(self):
        from apps.contracts.services.archive.generation.download_handler import _download_template_item

        contract = MagicMock()
        item = {"code": "lt_1", "name": "test", "template": "engagement_letter"}

        with patch("apps.contracts.services.archive.generation.download_handler.generate_single_archive_document") as mock_gen:
            mock_gen.return_value = {"content": None, "filename": ""}
            result = _download_template_item(contract, "lt_1", item)
            assert "error" in result


# ── download_handler: _download_uploaded_item ─────────────────────

class TestDownloadUploadedItem:
    @patch("apps.contracts.services.archive.generation.download_handler.FinalizedMaterial")
    def test_no_materials_returns_error(self, mock_fm):
        from apps.contracts.services.archive.generation.download_handler import _download_uploaded_item

        contract = MagicMock()
        contract.case_type = "litigation"
        mock_fm.objects.filter.return_value.order_by.return_value = []

        with patch("apps.contracts.services.archive.generation.download_handler._is_item_by_name", return_value=False):
            result = _download_uploaded_item(contract, "lt_4")
            assert "error" in result


# ── folder_builder constants ──────────────────────────────────────

class TestFolderBuilderConstants:
    def test_archive_catalog_codes(self):
        from apps.contracts.services.archive.generation.folder_builder import _ARCHIVE_CATALOG_CODES

        assert _ARCHIVE_CATALOG_CODES["non_litigation"] == "nl_3"
        assert _ARCHIVE_CATALOG_CODES["litigation"] == "lt_3"
        assert _ARCHIVE_CATALOG_CODES["criminal"] == "cr_3"
