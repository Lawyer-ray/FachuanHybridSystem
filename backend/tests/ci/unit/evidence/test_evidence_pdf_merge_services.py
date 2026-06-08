"""evidence/services/ + documents/services/infrastructure/ 单元测试。"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence.services.infrastructure.pdf_merge_service import (
    PDFMergeService,
    PDFMergeValidator,
    PDFMergeWorkflow,
)


class TestPDFMergeValidatorConstants:
    def test_supported_formats(self) -> None:
        assert ".pdf" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".docx" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".jpg" in PDFMergeValidator.SUPPORTED_FORMATS

    def test_image_formats(self) -> None:
        assert ".jpg" in PDFMergeValidator.IMAGE_FORMATS
        assert ".png" in PDFMergeValidator.IMAGE_FORMATS

    def test_word_formats(self) -> None:
        assert ".doc" in PDFMergeValidator.WORD_FORMATS
        assert ".docx" in PDFMergeValidator.WORD_FORMATS


class TestPDFMergeValidatorAssertSupportedFormat:
    def test_supported_format_passes(self) -> None:
        validator = PDFMergeValidator()
        validator.assert_supported_format(".pdf", "/path/to/file.pdf")

    def test_unsupported_format_raises(self) -> None:
        validator = PDFMergeValidator()
        with pytest.raises(Exception) as exc_info:
            validator.assert_supported_format(".xyz", "/path/to/file.xyz")
        assert "不支持" in str(exc_info.value)


class TestPDFMergeWorkflowInit:
    def test_default_validator(self) -> None:
        workflow = PDFMergeWorkflow()
        assert workflow._validator is None

    def test_validator_lazy_load(self) -> None:
        workflow = PDFMergeWorkflow()
        v = workflow.validator
        assert isinstance(v, PDFMergeValidator)
        assert workflow.validator is v


class TestPDFMergeWorkflowConvertToPdf:
    def test_pdf_returns_same_path(self) -> None:
        workflow = PDFMergeWorkflow()
        result = workflow.convert_to_pdf("/path/to/file.pdf")
        assert result == "/path/to/file.pdf"

    def test_unsupported_format_raises(self) -> None:
        workflow = PDFMergeWorkflow()
        with pytest.raises(Exception):  # noqa: B017
            workflow.convert_to_pdf("/path/to/file.xyz")


class TestPDFMergeWorkflowGenerateFilename:
    @patch("apps.evidence.services.infrastructure.pdf_merge_service.FilenameTemplateService")
    @patch("apps.evidence.services.infrastructure.pdf_merge_service.timezone")
    def test_basic_filename(self, mock_tz: MagicMock, mock_fts: MagicMock) -> None:
        mock_tz.now.return_value.strftime.return_value = "20260607"
        mock_fts.render_generated_doc.return_value = "证据明细一(测试案)V1_20260607"
        workflow = PDFMergeWorkflow()
        evidence_list = MagicMock()
        evidence_list.case.name = "测试案"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        result = workflow._generate_merged_filename(evidence_list)
        assert result.endswith(".pdf")


class TestPDFMergeService:
    def test_workflow_lazy_load(self) -> None:
        svc = PDFMergeService()
        assert svc._workflow is None
        w = svc.workflow
        assert isinstance(w, PDFMergeWorkflow)


class TestEvidenceExportServiceInit:
    def test_default_placeholder_service(self) -> None:
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        assert svc._placeholder_service is None

    def test_injected_placeholder_service(self) -> None:
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        mock_ps = MagicMock()
        svc = EvidenceExportService(placeholder_service=mock_ps)
        assert svc._placeholder_service is mock_ps
        assert svc.placeholder_service is mock_ps


class TestDocumentsEvidenceExportServiceInit:
    def test_default(self) -> None:
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        assert svc._placeholder_service is None

    def test_injected(self) -> None:
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService
        mock_ps = MagicMock()
        svc = EvidenceExportService(placeholder_service=mock_ps)
        assert svc.placeholder_service is mock_ps


class TestPdfMergeUtilsModule:
    def test_add_page_numbers_function_exists(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import add_page_numbers
        assert callable(add_page_numbers)

    def test_convert_image_to_pdf_function_exists(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_image_to_pdf
        assert callable(convert_image_to_pdf)

    def test_convert_docx_to_pdf_function_exists(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf
        assert callable(convert_docx_to_pdf)
