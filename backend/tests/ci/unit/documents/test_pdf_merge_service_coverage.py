"""Tests for pdf_merge_service — coverage for uncovered branches."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import BusinessException, ValidationException
from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator, PDFMergeWorkflow


class TestPDFMergeValidator:
    def test_get_items_no_files_raises(self) -> None:
        validator = PDFMergeValidator()
        mock_el = MagicMock()
        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        mock_el.items.filter.return_value.exclude.return_value.order_by.return_value = mock_qs
        with pytest.raises(ValidationException, match="没有任何文件"):
            validator.get_items(mock_el)

    def test_get_items_with_files(self) -> None:
        validator = PDFMergeValidator()
        mock_el = MagicMock()
        mock_el.pk = 1
        mock_item = MagicMock()
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        mock_qs.__iter__ = lambda self: iter([mock_item])
        mock_el.items.filter.return_value.exclude.return_value.order_by.return_value = mock_qs
        result = validator.get_items(mock_el)
        assert result is not None

    def test_assert_supported_format_valid(self) -> None:
        validator = PDFMergeValidator()
        validator.assert_supported_format(".pdf", "test.pdf")  # Should not raise

    def test_assert_supported_format_invalid(self) -> None:
        validator = PDFMergeValidator()
        with pytest.raises(BusinessException, match="不支持的文件格式"):
            validator.assert_supported_format(".xyz", "test.xyz")

    def test_supported_formats_class_var(self) -> None:
        assert ".pdf" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".docx" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".jpg" in PDFMergeValidator.SUPPORTED_FORMATS


class TestPDFMergeWorkflowInit:
    def test_default_validator(self) -> None:
        wf = PDFMergeWorkflow()
        assert isinstance(wf.validator, PDFMergeValidator)

    def test_injected_validator(self) -> None:
        mock_v = MagicMock()
        wf = PDFMergeWorkflow(validator=mock_v)
        assert wf.validator is mock_v


class TestPDFMergeWorkflowGenerateFilename:
    def test_title_starts_with_evidence_list(self) -> None:
        wf = PDFMergeWorkflow()
        mock_el = MagicMock()
        mock_el.case.name = "张三诉李四"
        mock_el.title = "证据清单（第一组）"
        mock_el.export_version = 1
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250101"
            result = wf._generate_merged_filename(mock_el)
            assert "证据明细（第一组）" in result
            assert "张三诉李四" in result
            assert "V1" in result

    def test_title_starts_with_supplementary(self) -> None:
        wf = PDFMergeWorkflow()
        mock_el = MagicMock()
        mock_el.case.name = "王五诉赵六"
        mock_el.title = "补充证据清单（第二组）"
        mock_el.export_version = 2
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250601"
            result = wf._generate_merged_filename(mock_el)
            assert "证据明细（第二组）" in result
            assert "王五诉赵六" in result

    def test_title_without_known_prefix(self) -> None:
        wf = PDFMergeWorkflow()
        mock_el = MagicMock()
        mock_el.case.name = "原告"
        mock_el.title = "其他标题"
        mock_el.export_version = 3
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250614"
            result = wf._generate_merged_filename(mock_el)
            assert "证据明细" in result
            # Since title doesn't start with either prefix, list_suffix is ""
            assert "V3" in result


class TestPDFMergeWorkflowMergeEvidence:
    def test_merge_success(self) -> None:
        mock_el = MagicMock()
        mock_item = MagicMock()
        mock_item.file.path = "/tmp/test.pdf"
        mock_item.file_name = "test.pdf"
        mock_item.id = 1

        mock_validator = MagicMock()
        # Use a MagicMock list that supports .count()
        mock_items_qs = MagicMock()
        mock_items_qs.count.return_value = 1
        mock_items_qs.__iter__ = MagicMock(return_value=iter([mock_item]))
        mock_validator.get_items.return_value = mock_items_qs
        mock_validator.IMAGE_FORMATS = [".jpg", ".jpeg", ".png"]
        mock_validator.WORD_FORMATS = [".doc", ".docx"]

        wf = PDFMergeWorkflow(validator=mock_validator)

        with (
            patch("pikepdf.Pdf") as mock_pdf_cls,
            patch("pikepdf.open") as mock_open,
            patch.object(wf, "add_page_numbers", return_value=b"pdf-bytes"),
            patch.object(wf, "_generate_merged_filename", return_value="merged.pdf"),
            patch.object(wf, "_save_merged_pdf"),
            patch.object(wf, "_cleanup_temp_files"),
        ):
            mock_pdf = MagicMock()
            mock_pdf_cls.new.return_value = mock_pdf
            mock_pdf.pages = []
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)

            mock_el.merged_pdf.path = "/tmp/merged.pdf"
            result = wf.merge_evidence_files(mock_el, progress_callback=None)
            assert result == "/tmp/merged.pdf"

    def test_merge_with_progress_callback(self) -> None:
        mock_el = MagicMock()
        mock_validator = MagicMock()
        progress_calls = []

        def progress(current: int, total: int, msg: str) -> None:
            progress_calls.append((current, total, msg))

        mock_item = MagicMock()
        mock_item.file.path = "/tmp/test.pdf"
        mock_item.file_name = "test.pdf"
        mock_item.id = 1

        mock_items_qs = MagicMock()
        mock_items_qs.count.return_value = 1
        mock_items_qs.__iter__ = MagicMock(return_value=iter([mock_item]))
        mock_validator.get_items.return_value = mock_items_qs
        mock_validator.IMAGE_FORMATS = [".jpg", ".jpeg", ".png"]
        mock_validator.WORD_FORMATS = [".doc", ".docx"]

        wf = PDFMergeWorkflow(validator=mock_validator)

        with (
            patch("pikepdf.Pdf") as mock_pdf_cls,
            patch("pikepdf.open") as mock_open,
            patch.object(wf, "add_page_numbers", return_value=b"bytes"),
            patch.object(wf, "_generate_merged_filename", return_value="file.pdf"),
            patch.object(wf, "_save_merged_pdf"),
            patch.object(wf, "_cleanup_temp_files"),
        ):
            mock_pdf = MagicMock()
            mock_pdf_cls.new.return_value = mock_pdf
            mock_pdf.pages = []
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            mock_el.merged_pdf.path = "/tmp/merged.pdf"
            wf.merge_evidence_files(mock_el, progress_callback=progress)
            assert len(progress_calls) >= 2

    def test_merge_exception_propagates_validation(self) -> None:
        mock_el = MagicMock()
        mock_validator = MagicMock()
        mock_validator.get_items.side_effect = ValidationException(message="no files")
        wf = PDFMergeWorkflow(validator=mock_validator)
        with pytest.raises(ValidationException):
            wf.merge_evidence_files(mock_el)

    def test_merge_generic_exception_wrapped(self) -> None:
        mock_el = MagicMock()
        mock_validator = MagicMock()
        mock_items_qs = MagicMock()
        mock_items_qs.count.return_value = 1
        mock_validator.get_items.return_value = mock_items_qs

        wf = PDFMergeWorkflow(validator=mock_validator)

        with (
            patch("pikepdf.Pdf", side_effect=RuntimeError("pikepdf broken")),
        ):
            with pytest.raises(BusinessException, match="PDF 合并失败"):
                wf.merge_evidence_files(mock_el)

    def test_merge_item_processing_error(self) -> None:
        mock_el = MagicMock()
        mock_validator = MagicMock()
        mock_item = MagicMock()
        mock_item.file.path = "/tmp/bad.pdf"
        mock_item.file_name = "bad.pdf"
        mock_item.id = 1

        mock_items_qs = MagicMock()
        mock_items_qs.count.return_value = 1
        mock_items_qs.__iter__ = MagicMock(return_value=iter([mock_item]))
        mock_validator.get_items.return_value = mock_items_qs

        wf = PDFMergeWorkflow(validator=mock_validator)

        with (
            patch("pikepdf.Pdf") as mock_pdf_cls,
            patch("pikepdf.open", side_effect=Exception("corrupt file")),
        ):
            mock_pdf = MagicMock()
            mock_pdf_cls.new.return_value = mock_pdf
            with pytest.raises(BusinessException, match="处理文件"):
                wf.merge_evidence_files(mock_el)


class TestPDFMergeService:
    def test_init(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        assert svc is not None
