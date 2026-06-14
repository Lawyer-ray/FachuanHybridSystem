"""Coverage round 4: recognize_document.py + info_extractor.py."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException, ServiceUnavailableError, RecognitionTimeoutError
from apps.document_recognition.services.data_classes import DocumentType


# ============================================================
# recognize_document.py
# ============================================================

class TestRecognizeCourtDocumentUsecase:
    def _make_ucase(self):
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import RecognizeCourtDocumentUsecase
        return RecognizeCourtDocumentUsecase(
            text_extraction=MagicMock(),
            classifier=MagicMock(),
            extractor=MagicMock(),
            binding_service=MagicMock(),
            document_renamer=MagicMock(),
        )

    def test_empty_text_extraction(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = ""
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        result = uc.execute(file_path="/tmp/test.pdf")
        assert result.recognition.document_type == DocumentType.OTHER
        assert result.binding is not None

    def test_extraction_failure(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = False
        ext_result.text = ""
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        result = uc.execute(file_path="/tmp/test.pdf")
        assert result.recognition.document_type == DocumentType.OTHER

    def test_summons_success(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "传票内容"
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        uc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.95)
        uc.extractor.extract_summons_info.return_value = {"case_number": "(2024)粤0604民初12345号", "court_time": datetime(2024, 6, 15, 9, 0)}
        uc.binding_service.find_case_by_number.return_value = 1
        case_dto = MagicMock()
        case_dto.name = "张某诉李某"
        uc.binding_service.case_service.get_case_by_id_internal.return_value = case_dto
        uc.binding_service.format_log_content.return_value = "log"
        uc.binding_service.bind_document_to_case.return_value = MagicMock()
        uc.document_renamer.generate_filename.return_value = "renamed.pdf"
        with patch("apps.document_recognition.usecases.court_document_recognition.recognize_document.FilenameTemplateService") as mock_ft:
            with patch("apps.core.utils.path.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.parent = MagicMock()
                mock_path.rename.return_value = None
                MockPath.return_value = mock_path
                mock_ft.get_unique_filepath.return_value = (mock_path, True)
                result = uc.execute(file_path="/tmp/test.pdf")
        assert result.recognition.document_type == DocumentType.SUMMONS

    def test_summons_no_case_number(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "传票"
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        uc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        uc.extractor.extract_summons_info.return_value = {"case_number": None, "court_time": None}
        result = uc.execute(file_path="/tmp/test.pdf")
        assert "未识别到案号" in result.binding.message

    def test_execution_ruling(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "裁定书"
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        uc.classifier.classify.return_value = (DocumentType.EXECUTION_RULING, 0.8)
        uc.extractor.extract_execution_info.return_value = {"case_number": "(2024)粤执123号", "preservation_deadline": "2025-01-01"}
        result = uc.execute(file_path="/tmp/test.pdf")
        assert "开发中" in result.binding.message

    def test_other_type(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "其他文书"
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        uc.classifier.classify.return_value = (DocumentType.OTHER, 0.5)
        result = uc.execute(file_path="/tmp/test.pdf")
        assert "暂时只支持" in result.binding.message

    def test_validation_exception_reraised(self):
        uc = self._make_ucase()
        uc.text_extraction.extract_text.side_effect = ValidationException("bad input")
        with pytest.raises(ValidationException):
            uc.execute(file_path="/tmp/test.pdf")

    def test_generic_exception_reraised(self):
        uc = self._make_ucase()
        uc.text_extraction.extract_text.side_effect = RuntimeError("unexpected")
        with pytest.raises(RuntimeError):
            uc.execute(file_path="/tmp/test.pdf")

    def test_rename_fallback_on_exception(self):
        uc = self._make_ucase()
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = "传票"
        ext_result.extraction_method = "ocr"
        uc.text_extraction.extract_text.return_value = ext_result
        uc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        uc.extractor.extract_summons_info.return_value = {"case_number": "(2024)粤123民初1号", "court_time": None}
        uc.binding_service.find_case_by_number.return_value = 1
        case_dto = MagicMock()
        case_dto.name = "案件名"
        uc.binding_service.case_service.get_case_by_id_internal.return_value = case_dto
        uc.binding_service.format_log_content.return_value = "log"
        uc.binding_service.bind_document_to_case.return_value = MagicMock()
        uc.document_renamer.generate_filename.side_effect = RuntimeError("rename fail")
        result = uc.execute(file_path="/tmp/test.pdf")
        assert result.file_path == "/tmp/test.pdf"

    def test_extract_key_info_summons(self):
        uc = self._make_ucase()
        uc.extractor.extract_summons_info.return_value = {"case_number": "CN1", "court_time": "T1"}
        cn, ct = uc._extract_key_info(DocumentType.SUMMONS, "text")
        assert cn == "CN1"

    def test_extract_key_info_execution(self):
        uc = self._make_ucase()
        uc.extractor.extract_execution_info.return_value = {"case_number": "CN2", "preservation_deadline": "DL"}
        cn, dl = uc._extract_key_info(DocumentType.EXECUTION_RULING, "text")
        assert cn == "CN2"

    def test_extract_key_info_other(self):
        uc = self._make_ucase()
        cn, ct = uc._extract_key_info(DocumentType.OTHER, "text")
        assert cn is None
        assert ct is None


# ============================================================
# info_extractor.py
# ============================================================

class TestInfoExtractor:
    def _make_extractor(self):
        from apps.document_recognition.services.info_extractor import InfoExtractor
        ext = InfoExtractor.__new__(InfoExtractor)
        ext.ollama_model = "test_model"
        ext.ollama_base_url = "http://localhost"
        ext._llm_service = MagicMock()
        return ext

    def test_extract_summons_empty_text(self):
        ext = self._make_extractor()
        result = ext.extract_summons_info("")
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_extract_summons_whitespace_only(self):
        ext = self._make_extractor()
        result = ext.extract_summons_info("   ")
        assert result["case_number"] is None

    def test_extract_execution_empty_text(self):
        ext = self._make_extractor()
        result = ext.extract_execution_info("")
        assert result["case_number"] is None
        assert result["preservation_deadline"] is None

    def test_extract_execution_whitespace_only(self):
        ext = self._make_extractor()
        result = ext.extract_execution_info("   ")
        assert result["case_number"] is None

    def test_extract_summons_with_regex_only(self):
        ext = self._make_extractor()
        with patch.object(ext, '_extract_case_number_by_regex', return_value="(2024)粤0604民初123号"):
            with patch.object(ext, '_extract_datetime_by_regex', return_value=[]):
                with patch("apps.document_recognition.services.info_extractor.chat", side_effect=RuntimeError("no llm")):
                    result = ext.extract_summons_info("传票内容包含(2024)粤0604民初123号")
        assert result["case_number"] == "(2024)粤0604民初123号"

    def test_extract_summons_llm_network_error_fallback(self):
        ext = self._make_extractor()
        from apps.core.llm.exceptions import LLMNetworkError
        with patch.object(ext, '_extract_case_number_by_regex', return_value=None):
            with patch.object(ext, '_extract_datetime_by_regex', return_value=[]):
                with patch("apps.document_recognition.services.info_extractor.chat", side_effect=LLMNetworkError("net err")):
                    result = ext.extract_summons_info("传票内容文字")
        assert result["case_number"] is None

    def test_extract_summons_llm_timeout_error_fallback(self):
        ext = self._make_extractor()
        from apps.core.llm.exceptions import LLMTimeoutError
        with patch.object(ext, '_extract_case_number_by_regex', return_value=None):
            with patch.object(ext, '_extract_datetime_by_regex', return_value=[]):
                with patch("apps.document_recognition.services.info_extractor.chat", side_effect=LLMTimeoutError("timeout")):
                    result = ext.extract_summons_info("传票内容文字")
        assert result["case_number"] is None

    def test_extract_execution_network_error_raises(self):
        ext = self._make_extractor()
        from apps.core.llm.exceptions import LLMNetworkError
        with patch("apps.document_recognition.services.info_extractor.chat", side_effect=LLMNetworkError("net")):
            with pytest.raises(ServiceUnavailableError):
                ext.extract_execution_info("裁定书内容")

    def test_extract_execution_timeout_raises(self):
        ext = self._make_extractor()
        from apps.core.llm.exceptions import LLMTimeoutError
        with patch("apps.document_recognition.services.info_extractor.chat", side_effect=LLMTimeoutError("timeout")):
            with pytest.raises(RecognitionTimeoutError):
                ext.extract_execution_info("裁定书内容")

    def test_extract_execution_generic_error_raises(self):
        ext = self._make_extractor()
        with patch("apps.document_recognition.services.info_extractor.chat", side_effect=RuntimeError("unexpected")):
            with pytest.raises(RuntimeError):
                ext.extract_execution_info("裁定书内容")

    def test_llm_service_lazy_property(self):
        ext = self._make_extractor()
        ext._llm_service = None
        with patch("apps.document_recognition.services.info_extractor.ServiceLocator") as MockSL:
            mock_llm = MagicMock()
            MockSL.get_llm_service.return_value = mock_llm
            assert ext.llm_service is mock_llm
            assert ext.llm_service is mock_llm
