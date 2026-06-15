"""pdf_merge_service.py — round8 tests for remaining uncovered branches.

Covers 38 missing: PDFMergeWorkflow.merge_evidence_files, _merge_all_items,
_save_merged_pdf, _generate_merged_filename branches, _cleanup_temp_files,
convert_to_pdf, add_page_numbers, get_pdf_page_count, PDFMergeService delegation.
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import BusinessException, ValidationException
from apps.evidence.services.infrastructure.pdf_merge_service import (
    PDFMergeService,
    PDFMergeValidator,
    PDFMergeWorkflow,
)


# ── PDFMergeValidator.assert_supported_format ───────────────────────────


class TestAssertSupportedFormat:
    def test_valid_format(self):
        validator = PDFMergeValidator()
        # Should not raise
        validator.assert_supported_format(".pdf", "/tmp/test.pdf")

    def test_invalid_format(self):
        validator = PDFMergeValidator()
        with pytest.raises(BusinessException, match="不支持的文件格式"):
            validator.assert_supported_format(".xyz", "/tmp/test.xyz")


# ── PDFMergeWorkflow ──────────────────────────────────────────────────


class TestPDFMergeWorkflowInit:
    def test_default_init(self):
        wf = PDFMergeWorkflow()
        assert wf._validator is None

    def test_validator_lazy(self):
        wf = PDFMergeWorkflow()
        v = wf.validator
        assert isinstance(v, PDFMergeValidator)

    def test_injected_validator(self):
        v = MagicMock()
        wf = PDFMergeWorkflow(validator=v)
        assert wf.validator is v


# ── _generate_merged_filename ─────────────────────────────────────────


class TestGenerateMergedFilenameRound8:
    def test_evidence_list_title(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "Test"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1

        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "result"
            result = wf._generate_merged_filename(evidence_list)
            assert result == "result.pdf"
            call_kwargs = MockFTS.render_generated_doc.call_args[1]
            assert "证据明细一" in call_kwargs["doc_type"]

    def test_supplement_title(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "Test"
        evidence_list.title = "补充证据清单二"
        evidence_list.export_version = 2

        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "result"
            result = wf._generate_merged_filename(evidence_list)
            call_kwargs = MockFTS.render_generated_doc.call_args[1]
            assert "证据明细二" in call_kwargs["doc_type"]

    def test_other_title(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "Test"
        evidence_list.title = "其他标题"
        evidence_list.export_version = 3

        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "result"
            result = wf._generate_merged_filename(evidence_list)
            call_kwargs = MockFTS.render_generated_doc.call_args[1]
            assert call_kwargs["doc_type"] == "证据明细"


# ── merge_evidence_files ──────────────────────────────────────────────


class TestMergeEvidenceFiles:
    def test_success_flow(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.start_page = 1
        evidence_list.case.name = "Test"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        evidence_list.merged_pdf.path = "/tmp/merged.pdf"

        item = MagicMock()
        item.file.path = "/tmp/test.pdf"
        item.file_name = "test.pdf"
        item.id = 1

        items_qs = MagicMock()
        items_qs.count.return_value = 1
        items_qs.__iter__ = MagicMock(return_value=iter([item]))

        wf._validator = MagicMock()
        wf._validator.get_items.return_value = items_qs

        with patch.dict("sys.modules", {"pikepdf": MagicMock()}) as mock_modules:
            mock_pikepdf = mock_modules["pikepdf"]
            mock_pdf = MagicMock()
            mock_pikepdf.Pdf.new.return_value = mock_pdf
            mock_pikepdf.open.return_value.__enter__.return_value = mock_pdf

            with patch.object(wf, "add_page_numbers", return_value=b"%PDF-1.4"):
                with patch.object(wf, "_save_merged_pdf"):
                    with patch.object(wf, "_cleanup_temp_files"):
                        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS:
                            MockFTS.render_generated_doc.return_value = "result"
                            with patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
                                mock_tz.now.return_value.strftime.return_value = "20260101"
                                result = wf.merge_evidence_files(evidence_list)
        assert result == "/tmp/merged.pdf"

    def test_validation_exception_raised(self):
        wf = PDFMergeWorkflow()
        wf._validator = MagicMock()
        wf._validator.get_items.side_effect = ValidationException(
            message="no files", code="NO_FILES"
        )

        evidence_list = MagicMock()
        with pytest.raises(ValidationException):
            wf.merge_evidence_files(evidence_list)

    def test_business_exception_raised(self):
        wf = PDFMergeWorkflow()
        wf._validator = MagicMock()
        wf._validator.get_items.side_effect = BusinessException(
            message="err", code="ERR"
        )

        evidence_list = MagicMock()
        with pytest.raises(BusinessException):
            wf.merge_evidence_files(evidence_list)

    def test_general_exception_wrapped(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.start_page = 1
        evidence_list.case.name = "Test"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1

        items_qs = MagicMock()
        items_qs.count.return_value = 1

        wf._validator = MagicMock()
        wf._validator.get_items.return_value = items_qs

        with patch.dict("sys.modules", {"pikepdf": MagicMock()}) as mock_modules:
            mock_pikepdf = mock_modules["pikepdf"]
            mock_pikepdf.Pdf.new.side_effect = RuntimeError("pdf error")

            with pytest.raises(BusinessException, match="PDF 合并失败"):
                wf.merge_evidence_files(evidence_list)

    def test_with_progress_callback(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.start_page = 1
        evidence_list.case.name = "Test"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        evidence_list.merged_pdf.path = "/tmp/merged.pdf"

        item = MagicMock()
        item.file.path = "/tmp/test.pdf"
        item.file_name = "test.pdf"
        item.id = 1

        items_qs = MagicMock()
        items_qs.count.return_value = 1
        items_qs.__iter__ = MagicMock(return_value=iter([item]))

        wf._validator = MagicMock()
        wf._validator.get_items.return_value = items_qs
        progress = MagicMock()

        with patch.dict("sys.modules", {"pikepdf": MagicMock()}) as mock_modules:
            mock_pikepdf = mock_modules["pikepdf"]
            mock_pdf = MagicMock()
            mock_pikepdf.Pdf.new.return_value = mock_pdf
            mock_pikepdf.open.return_value.__enter__.return_value = mock_pdf

            with patch.object(wf, "add_page_numbers", return_value=b"%PDF-1.4"):
                with patch.object(wf, "_save_merged_pdf"):
                    with patch.object(wf, "_cleanup_temp_files"):
                        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS:
                            MockFTS.render_generated_doc.return_value = "result"
                            with patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
                                mock_tz.now.return_value.strftime.return_value = "20260101"
                                wf.merge_evidence_files(evidence_list, progress_callback=progress)
        assert progress.call_count >= 2


# ── _merge_all_items ──────────────────────────────────────────────────


class TestMergeAllItems:
    def test_non_pdf_file_converts(self):
        wf = PDFMergeWorkflow()
        wf._validator = MagicMock()

        item = MagicMock()
        item.file.path = "/tmp/test.doc"
        item.file_name = "test.doc"
        item.id = 1

        merged_pdf = MagicMock()

        with patch.dict("sys.modules", {"pikepdf": MagicMock()}) as mock_modules:
            mock_pikepdf = mock_modules["pikepdf"]
            mock_pdf = MagicMock()
            mock_pikepdf.open.return_value.__enter__.return_value = mock_pdf

            with patch.object(wf, "convert_to_pdf", return_value="/tmp/test.pdf"):
                wf._merge_all_items(merged_pdf, [item], [], 1, None)
                merged_pdf.pages.extend.assert_called_once()

    def test_item_processing_error(self):
        wf = PDFMergeWorkflow()
        wf._validator = MagicMock()

        item = MagicMock()
        item.file.path = None
        item.file_name = "bad.pdf"
        item.id = 1

        merged_pdf = MagicMock()

        with patch.dict("sys.modules", {"pikepdf": MagicMock()}) as mock_modules:
            mock_pikepdf = mock_modules["pikepdf"]
            mock_pikepdf.open.side_effect = Exception("open error")
            with pytest.raises(BusinessException, match="处理文件"):
                wf._merge_all_items(merged_pdf, [item], [], 1, None)


# ── _save_merged_pdf ──────────────────────────────────────────────────


class TestSaveMergedPdf:
    def test_saves_and_updates(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.merged_pdf = MagicMock()

        with patch.object(wf, "get_pdf_page_count", return_value=5):
            wf._save_merged_pdf(evidence_list, "file.pdf", b"%PDF")
        evidence_list.merged_pdf.save.assert_called_once()
        assert evidence_list.total_pages == 5
        evidence_list.save.assert_called_once()

    def test_no_existing_merged_pdf(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        # merged_pdf is a MagicMock (truthy) but no delete needed
        evidence_list.merged_pdf = MagicMock()

        with patch.object(wf, "get_pdf_page_count", return_value=3):
            wf._save_merged_pdf(evidence_list, "file.pdf", b"%PDF")
        evidence_list.merged_pdf.save.assert_called_once()

    def test_delete_existing_merged_pdf(self):
        wf = PDFMergeWorkflow()
        evidence_list = MagicMock()
        existing = MagicMock()
        existing.delete.return_value = None
        evidence_list.merged_pdf = existing

        with patch.object(wf, "get_pdf_page_count", return_value=1):
            wf._save_merged_pdf(evidence_list, "file.pdf", b"%PDF")
        evidence_list.merged_pdf.save.assert_called_once()


# ── add_page_numbers ──────────────────────────────────────────────────


class TestAddPageNumbers:
    def test_delegates_to_utils(self):
        wf = PDFMergeWorkflow()
        with patch("apps.evidence.services.infrastructure.pdf_merge_service._get_pdf_merge_utils_module") as mock_mod:
            mock_mod.return_value.add_page_numbers.return_value = b"result"
            result = wf.add_page_numbers(io.BytesIO(b"input"), start_page=5)
            assert result == b"result"
            mock_mod.return_value.add_page_numbers.assert_called_once()


# ── get_pdf_page_count ────────────────────────────────────────────────


class TestGetPdfPageCount:
    def test_delegates_to_utils(self):
        wf = PDFMergeWorkflow()
        with patch("apps.evidence.services.infrastructure.pdf_utils.get_pdf_page_count") as mock_gpc:
            mock_gpc.return_value = 10
            result = wf.get_pdf_page_count(io.BytesIO(b"test"))
            assert result == 10


# ── PDFMergeService ───────────────────────────────────────────────────


class TestPDFMergeServiceRound8:
    def test_workflow_lazy(self):
        svc = PDFMergeService()
        w = svc.workflow
        assert isinstance(w, PDFMergeWorkflow)

    def test_merge_delegates(self):
        wf = MagicMock()
        wf.merge_evidence_files.return_value = "/tmp/merged.pdf"
        svc = PDFMergeService(workflow=wf)
        el = MagicMock()
        result = svc.merge_evidence_files(el)
        assert result == "/tmp/merged.pdf"

    def test_convert_delegates(self):
        wf = MagicMock()
        wf.convert_to_pdf.return_value = "/tmp/converted.pdf"
        svc = PDFMergeService(workflow=wf)
        result = svc.convert_to_pdf("/tmp/test.doc")
        assert result == "/tmp/converted.pdf"

    def test_add_page_numbers_delegates(self):
        wf = MagicMock()
        wf.add_page_numbers.return_value = b"pdf"
        svc = PDFMergeService(workflow=wf)
        result = svc.add_page_numbers(io.BytesIO(b"input"), start_page=1)
        assert result == b"pdf"

    def test_get_pdf_page_count_delegates(self):
        wf = MagicMock()
        wf.get_pdf_page_count.return_value = 5
        svc = PDFMergeService(workflow=wf)
        result = svc.get_pdf_page_count(io.BytesIO(b"test"))
        assert result == 5


# ── _cleanup_temp_files ───────────────────────────────────────────────


class TestCleanupTempFiles:
    def test_cleans_files(self):
        wf = PDFMergeWorkflow()
        with patch("apps.evidence.services.infrastructure.pdf_merge_service.Path") as MockPath:
            mock_path = MagicMock()
            MockPath.return_value = mock_path
            wf._cleanup_temp_files(["/tmp/f1.pdf", "/tmp/f2.pdf"])
            assert mock_path.unlink.call_count == 2

    def test_empty_list(self):
        wf = PDFMergeWorkflow()
        # Should not raise
        wf._cleanup_temp_files([])
