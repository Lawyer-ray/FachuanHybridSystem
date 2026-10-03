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
    def test_file_not_exists(self, mock_material_model, tmp_path):
        from django.conf import settings

        material = MagicMock()
        material.file_path = "contracts/finalized/1/missing.pdf"
        material.original_filename = "test.pdf"
        mock_material_model.objects.filter.return_value.order_by.return_value = [material]

        media = tmp_path / "media"
        media.mkdir()

        with patch.object(settings, "MEDIA_ROOT", str(media)):
            contract = MagicMock()
            result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert len(result["errors"]) > 0


class TestReplaceMaterialFile:
    """A4 缩放替换：先写新文件、再删旧文件、回写 file_path。"""

    def test_save_new_then_delete_old(self, tmp_path):
        from django.test import override_settings

        from apps.contracts.services.archive.generation.pdf_utils import _replace_material_file

        media = tmp_path / "media"
        old_file = media / "contracts" / "finalized" / "1" / "old.pdf"
        old_file.parent.mkdir(parents=True)
        old_file.write_bytes(b"old-content")

        material = MagicMock()
        material.file_path = "contracts/finalized/1/old.pdf"

        # override_settings 触发 setting_changed，刷新 FileSystemStorage 的 location 缓存；
        # 直接 patch.object(settings, ...) 不会，测试顺序一变就会错乱
        with override_settings(MEDIA_ROOT=str(media)):
            _replace_material_file(material, b"scaled-content")

        # 旧文件已删除，新文件内容正确，DB 路径已回写
        assert not old_file.exists()
        new_rel = material.file_path
        assert new_rel != "contracts/finalized/1/old.pdf"
        assert (media / new_rel).read_bytes() == b"scaled-content"
        material.save.assert_called_once_with(update_fields=["file_path"])


class TestAddPageNumbers:
    def test_add_page_numbers(self):
        import pymupdf as fitz

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

    def test_merge_with_nonexistent_files(self, tmp_path):
        from django.conf import settings

        material = MagicMock()
        material.file_path = "contracts/finalized/1/missing.pdf"
        material.original_filename = "test.pdf"

        media = tmp_path / "media"
        media.mkdir()

        with patch.object(settings, "MEDIA_ROOT", str(media)):
            result = merge_materials_to_single_pdf([material])
        # No files could be opened, so merged_doc is empty
        assert result["success"] is False
