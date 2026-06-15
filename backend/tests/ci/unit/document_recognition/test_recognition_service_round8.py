"""recognition_service.py — round8 tests.

Covers 39 missing: recognize_document, recognize_document_from_text,
_build_binding, _extract_doc_info, lazy-load properties.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    RecognitionResult,
    RecognitionResponse,
)
from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService


def _make_service(**overrides):
    return CourtDocumentRecognitionService(
        text_extraction=overrides.get("text_extraction", MagicMock()),
        classifier=overrides.get("classifier", MagicMock()),
        extractor=overrides.get("extractor", MagicMock()),
        binding_service=overrides.get("binding_service", MagicMock()),
        document_renamer=overrides.get("document_renamer", MagicMock()),
    )


# ── lazy-load properties ───────────────────────────────────────────────


class TestLazyLoadProperties:
    def test_text_extraction_lazy(self):
        svc = CourtDocumentRecognitionService()
        with patch("apps.document_recognition.services.text_extraction_service.TextExtractionService") as MockTES:
            te = svc.text_extraction
            assert te is not None

    def test_classifier_lazy(self):
        svc = CourtDocumentRecognitionService()
        with patch("apps.document_recognition.services.document_classifier.DocumentClassifier") as MockDC:
            c = svc.classifier
            assert c is not None

    def test_extractor_lazy(self):
        svc = CourtDocumentRecognitionService()
        with patch("apps.document_recognition.services.info_extractor.InfoExtractor") as MockIE:
            e = svc.extractor
            assert e is not None

    def test_binding_service_lazy(self):
        svc = CourtDocumentRecognitionService()
        with patch("apps.document_recognition.services.case_binding_service.CaseBindingService") as MockCBS:
            bs = svc.binding_service
            assert bs is not None

    def test_document_renamer_lazy(self):
        svc = CourtDocumentRecognitionService()
        with patch("apps.automation.services.sms.document_renamer.DocumentRenamer") as MockDR:
            dr = svc.document_renamer
            assert dr is not None


# ── _extract_doc_info ──────────────────────────────────────────────────


class TestExtractDocInfo:
    def test_summons(self):
        svc = _make_service()
        svc.extractor.extract_summons_info.return_value = {
            "case_number": "（2024）京01民初123号",
            "court_time": datetime(2024, 6, 15),
        }
        cn, kt = svc._extract_doc_info(DocumentType.SUMMONS, "text")
        assert cn == "（2024）京01民初123号"
        assert kt == datetime(2024, 6, 15)

    def test_execution_ruling(self):
        svc = _make_service()
        svc.extractor.extract_execution_info.return_value = {
            "case_number": "（2024）京01执123号",
            "preservation_deadline": datetime(2024, 7, 1),
        }
        # Use a mock doc_type with value "execution_ruling" to match the source code check
        mock_doc_type = MagicMock()
        mock_doc_type.value = "execution_ruling"
        cn, kt = svc._extract_doc_info(mock_doc_type, "text")
        assert cn == "（2024）京01执123号"
        assert kt == datetime(2024, 7, 1)

    def test_other_type(self):
        svc = _make_service()
        cn, kt = svc._extract_doc_info(DocumentType.OTHER, "text")
        assert cn is None
        assert kt is None


# ── _build_binding ─────────────────────────────────────────────────────


class TestBuildBinding:
    def test_summons_with_case_number(self):
        svc = _make_service()
        svc.binding_service.find_case_by_number.return_value = 1
        case_dto = MagicMock()
        case_dto.name = "张三诉李四"
        svc.binding_service.case_service.get_case_by_id_internal.return_value = case_dto
        svc.binding_service.format_log_content.return_value = "log content"
        svc.binding_service.bind_document_to_case.return_value = BindingResult.success_result(
            case_id=1, case_name="张三诉李四", case_log_id=10
        )
        svc.document_renamer.generate_filename.return_value = "new_name.pdf"

        with patch("apps.core.services.filename_template_service.FilenameTemplateService") as MockFTS:
            MockFTS.get_unique_filepath.return_value = (SimpleNamespace(as_posix=lambda: "/tmp/new.pdf"), None)
            with patch("pathlib.Path") as MockPath:
                mock_orig = MagicMock()
                MockPath.return_value = mock_orig
                mock_orig.parent = "/tmp"
                mock_orig.name = "test.pdf"
                mock_orig.as_posix.return_value = "/tmp/test.pdf"

                binding, renamed = svc._build_binding(
                    DocumentType.SUMMONS, "（2024）京01民初123号",
                    datetime(2024, 6, 15), "/tmp/test.pdf", "text", None,
                )
        assert binding.success

    def test_summons_no_case_number(self):
        svc = _make_service()
        svc.binding_service.find_case_by_number.return_value = None
        svc.binding_service.format_log_content.return_value = "log"
        svc.binding_service.bind_document_to_case.return_value = BindingResult.success_result(
            case_id=1, case_name="Test", case_log_id=10
        )

        binding, renamed = svc._build_binding(
            DocumentType.SUMMONS, None, None, "/tmp/test.pdf", "text", None,
        )
        assert renamed == "/tmp/test.pdf"

    def test_other_type(self):
        svc = _make_service()
        binding, renamed = svc._build_binding(
            DocumentType.OTHER, None, None, "/tmp/test.pdf", "text", None,
        )
        assert not binding.success
        assert binding.error_code == "UNSUPPORTED_DOCUMENT_TYPE"

    def test_execution_ruling_type(self):
        svc = _make_service()
        binding, renamed = svc._build_binding(
            DocumentType.EXECUTION_RULING, "123", None, "/tmp/test.pdf", "text", None,
        )
        assert not binding.success
        assert binding.error_code == "FEATURE_NOT_IMPLEMENTED"

    def test_no_case_name_no_rename(self):
        svc = _make_service()
        svc.binding_service.find_case_by_number.return_value = 1
        svc.binding_service.case_service.get_case_by_id_internal.return_value = None
        svc.binding_service.format_log_content.return_value = "log"
        svc.binding_service.bind_document_to_case.return_value = BindingResult.success_result(
            case_id=1, case_name="Test", case_log_id=10
        )

        binding, renamed = svc._build_binding(
            DocumentType.SUMMONS, "123", None, "/tmp/test.pdf", "text", None,
        )
        assert renamed == "/tmp/test.pdf"


# ── recognize_document ─────────────────────────────────────────────────


class TestRecognizeDocument:
    def test_text_extraction_fails(self):
        svc = _make_service()
        ext_result = MagicMock()
        ext_result.success = False
        ext_result.extraction_method = "pdf_direct"
        ext_result.text = ""
        svc.text_extraction.extract_text.return_value = ext_result

        response = svc.recognize_document("/tmp/test.pdf")
        assert not response.binding.success
        assert response.recognition.document_type == DocumentType.OTHER

    def test_text_extraction_empty(self):
        svc = _make_service()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = ""
        ext_result.extraction_method = "pdf_direct"
        svc.text_extraction.extract_text.return_value = ext_result

        response = svc.recognize_document("/tmp/test.pdf")
        assert not response.binding.success

    def test_successful_recognition(self):
        svc = _make_service()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "传票内容"
        ext_result.extraction_method = "pdf_direct"
        svc.text_extraction.extract_text.return_value = ext_result
        svc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        svc.extractor.extract_summons_info.return_value = {
            "case_number": "123",
            "court_time": datetime(2024, 6, 15),
        }
        svc.binding_service.find_case_by_number.return_value = 1
        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.binding_service.case_service.get_case_by_id_internal.return_value = case_dto
        svc.binding_service.format_log_content.return_value = "log"
        svc.binding_service.bind_document_to_case.return_value = BindingResult.success_result(
            case_id=1, case_name="Test", case_log_id=10
        )

        with patch("apps.core.services.filename_template_service.FilenameTemplateService") as MockFTS:
            MockFTS.get_unique_filepath.return_value = (SimpleNamespace(as_posix=lambda: "/tmp/new.pdf"), None)
            with patch("pathlib.Path") as MockPath:
                mock_orig = MagicMock()
                MockPath.return_value = mock_orig
                mock_orig.parent = "/tmp"
                mock_orig.name = "test.pdf"

                response = svc.recognize_document("/tmp/test.pdf")
        assert response.recognition.document_type == DocumentType.SUMMONS

    def test_general_exception(self):
        svc = _make_service()
        svc.text_extraction.extract_text.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            svc.recognize_document("/tmp/test.pdf")

    def test_validation_exception_reraised(self):
        svc = _make_service()
        svc.text_extraction.extract_text.side_effect = ValidationException(
            message="bad", code="BAD"
        )

        with pytest.raises(ValidationException):
            svc.recognize_document("/tmp/test.pdf")


# ── recognize_document_from_text ───────────────────────────────────────


class TestRecognizeDocumentFromText:
    def test_empty_text(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="不能为空"):
            svc.recognize_document_from_text("")

    def test_whitespace_only(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="不能为空"):
            svc.recognize_document_from_text("   ")

    def test_summons_recognition(self):
        svc = _make_service()
        svc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.85)
        svc.extractor.extract_summons_info.return_value = {
            "case_number": "123",
            "court_time": datetime(2024, 6, 15),
        }

        result = svc.recognize_document_from_text("传票内容")
        assert result.document_type == DocumentType.SUMMONS
        assert result.case_number == "123"

    def test_execution_ruling_recognition(self):
        svc = _make_service()
        svc.classifier.classify.return_value = (DocumentType.EXECUTION_RULING, 0.8)
        svc.extractor.extract_execution_info.return_value = {
            "case_number": "456",
            "preservation_deadline": datetime(2024, 7, 1),
        }

        result = svc.recognize_document_from_text("执行裁定书")
        assert result.document_type == DocumentType.EXECUTION_RULING
        assert result.key_time == datetime(2024, 7, 1)

    def test_other_type_recognition(self):
        svc = _make_service()
        svc.classifier.classify.return_value = (DocumentType.OTHER, 0.5)

        result = svc.recognize_document_from_text("判决书")
        assert result.document_type == DocumentType.OTHER
        assert result.case_number is None

    def test_general_exception(self):
        svc = _make_service()
        svc.classifier.classify.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            svc.recognize_document_from_text("text")

    def test_validation_exception_reraised(self):
        svc = _make_service()
        svc.classifier.classify.side_effect = ValidationException(
            message="bad", code="BAD"
        )

        with pytest.raises(ValidationException):
            svc.recognize_document_from_text("text")

    def test_extraction_method_is_text_input(self):
        svc = _make_service()
        svc.classifier.classify.return_value = (DocumentType.OTHER, 0.5)

        result = svc.recognize_document_from_text("hello")
        assert result.extraction_method == "text_input"
