"""evidence/services/infrastructure/pdf_merge_service.py 单元测试。"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import BusinessException, ValidationException
from apps.evidence.services.infrastructure.pdf_merge_service import (
    PDFMergeService,
    PDFMergeValidator,
    PDFMergeWorkflow,
)


# ── PDFMergeValidator.get_items ────────────────────────────────────────


class TestPDFMergeValidatorGetItems:
    def test_no_files_raises(self) -> None:
        validator = PDFMergeValidator()
        evidence_list = MagicMock()
        evidence_list.items.filter.return_value.exclude.return_value.order_by.return_value.exists.return_value = False
        with pytest.raises(ValidationException):
            validator.get_items(evidence_list)


# ── PDFMergeWorkflow._generate_merged_filename ────────────────────────


class TestGenerateMergedFilename:
    def test_with_evidence_prefix(self) -> None:
        workflow = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "Test"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "evidence_Test_V1_20260101"
            result = workflow._generate_merged_filename(evidence_list)
            assert result.endswith(".pdf")

    def test_supplement_evidence_prefix(self) -> None:
        workflow = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "Test"
        evidence_list.title = "补充证据清单二"
        evidence_list.export_version = 2
        with patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "result"
            result = workflow._generate_merged_filename(evidence_list)
            call_kwargs = MockFTS.render_generated_doc.call_args[1]
            assert "二" in call_kwargs["doc_type"]


# ── PDFMergeWorkflow.get_pdf_page_count ───────────────────────────────


class TestGetPdfPageCount:
    def test_delegates_to_utils(self) -> None:
        workflow = PDFMergeWorkflow()
        with patch("apps.evidence.services.infrastructure.pdf_utils.get_pdf_page_count", return_value=5):
            result = workflow.get_pdf_page_count(io.BytesIO(b"fake"))
            assert result == 5


# ── PDFMergeWorkflow._merge_all_items ─────────────────────────────────


class TestMergeAllItems:
    def test_item_processing_error(self) -> None:
        workflow = PDFMergeWorkflow()
        validator = MagicMock()
        workflow._validator = validator

        item = MagicMock()
        item.file.path = "/path/to/file.xyz"
        item.file_name = "bad.xyz"

        merged_pdf = MagicMock()
        merged_pdf.pages = MagicMock()

        with patch("pathlib.Path") as MockPath:
            mock_instance = MagicMock()
            mock_instance.suffix = ".xyz"
            MockPath.return_value = mock_instance
            with pytest.raises(BusinessException):
                workflow._merge_all_items(merged_pdf, [item], [], 1, None)


# ── PDFMergeWorkflow.add_page_numbers ─────────────────────────────────


class TestAddPageNumbers:
    def test_delegates(self) -> None:
        workflow = PDFMergeWorkflow()
        with patch("apps.evidence.services.infrastructure.pdf_merge_service._get_pdf_merge_utils_module") as mock_mod:
            mock_mod.return_value.add_page_numbers.return_value = b"pdf_bytes"
            result = workflow.add_page_numbers(io.BytesIO(b"input"), start_page=1)
            assert result == b"pdf_bytes"


# ── PDFMergeService lazy loading ──────────────────────────────────────


class TestPDFMergeServiceLazy:
    def test_default_workflow(self) -> None:
        svc = PDFMergeService()
        assert svc._workflow is None

    def test_workflow_property(self) -> None:
        svc = PDFMergeService()
        wf = svc.workflow
        assert isinstance(wf, PDFMergeWorkflow)
        assert svc.workflow is wf


class TestPDFMergeServiceDelegation:
    def test_merge_delegates(self) -> None:
        mock_wf = MagicMock()
        mock_wf.merge_evidence_files.return_value = "/path"
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.merge_evidence_files(MagicMock()) == "/path"

    def test_convert_delegates(self) -> None:
        mock_wf = MagicMock()
        mock_wf.convert_to_pdf.return_value = "/converted"
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.convert_to_pdf("/f.pdf") == "/converted"

    def test_page_count_delegates(self) -> None:
        mock_wf = MagicMock()
        mock_wf.get_pdf_page_count.return_value = 10
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.get_pdf_page_count(io.BytesIO(b"data")) == 10
