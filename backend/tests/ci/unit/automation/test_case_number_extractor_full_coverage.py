"""Comprehensive tests for automation.services.sms.case_number_extractor_service.

Covers: extract_from_document, extract_from_content, _build_extract_prompt,
_parse_ollama_response, validate_and_normalize, _normalize_single,
sync_to_case, _get_existing_numbers, _write_new_numbers, _extract_fallback,
_regex_extract_numbers, _deduplicate, lazy properties.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestCaseNumberExtractorService:
    """Test suite for CaseNumberExtractorService."""

    def _make_service(self, **kwargs):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService(**kwargs)


# ---------------------------------------------------------------------------
# extract_from_document
# ---------------------------------------------------------------------------


class TestExtractFromDocument:
    def _svc(self, **kw):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService(**kw)

    def test_empty_path(self):
        svc = self._svc()
        assert svc.extract_from_document("") == []

    def test_none_path(self):
        svc = self._svc()
        assert svc.extract_from_document(None) == []

    def test_successful_extraction(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.return_value = {"text": "（2025）粤01民初1号 案件内容"}
        svc = self._svc(document_processing_service=doc_svc, extraction_provider=MagicMock())
        svc.extract_from_content = MagicMock(return_value=["（2025）粤01民初1号"])
        result = svc.extract_from_document("/tmp/doc.pdf")
        assert result == ["（2025）粤01民初1号"]

    def test_no_text_content(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.return_value = {"text": ""}
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_none_result(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.return_value = None
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_no_text_key(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.return_value = {"other": "data"}
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_connection_error(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.side_effect = ConnectionError("refused")
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_file_not_found(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.side_effect = FileNotFoundError("no file")
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_generic_exception(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.side_effect = RuntimeError("boom")
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []

    def test_spaces_removed_from_content(self):
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.return_value = {"text": "（2025） 粤 01 民 初 1 号"}
        svc = self._svc(document_processing_service=doc_svc)
        svc.extract_from_content = MagicMock(return_value=[])
        svc.extract_from_document("/tmp/doc.pdf")
        # The content passed to extract_from_content should have spaces removed
        called_content = svc.extract_from_content.call_args[0][0]
        assert " " not in called_content
        assert "　" not in called_content

    def test_llm_error(self):
        from apps.core.llm.exceptions import LLMError
        doc_svc = MagicMock()
        doc_svc.extract_document_content_by_path_internal.side_effect = LLMError("fail")
        svc = self._svc(document_processing_service=doc_svc)
        assert svc.extract_from_document("/tmp/doc.pdf") == []


# ---------------------------------------------------------------------------
# extract_from_content
# ---------------------------------------------------------------------------


class TestExtractFromContent:
    def _svc(self, **kw):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService(**kw)

    def test_empty_content(self):
        svc = self._svc()
        assert svc.extract_from_content("") == []

    def test_whitespace_only(self):
        svc = self._svc()
        assert svc.extract_from_content("   ") == []

    def test_extraction_provider_used(self):
        provider = MagicMock()
        provider.extract.return_value = '{"case_numbers": ["（2025）粤01民初1号"]}'
        svc = self._svc(extraction_provider=provider)
        svc.validate_and_normalize = MagicMock(return_value=["（2025）粤01民初1号"])
        result = svc.extract_from_content("some content")
        provider.extract.assert_called_once()

    def test_extraction_provider_exception(self):
        provider = MagicMock()
        provider.extract.side_effect = RuntimeError("boom")
        svc = self._svc(extraction_provider=provider)
        assert svc.extract_from_content("content") == []

    def test_llm_service_used(self):
        llm = MagicMock()
        llm.chat.return_value = MagicMock(content='{"case_numbers": ["（2025）粤01民初1号"]}')
        svc = self._svc(llm_service=llm)
        svc.validate_and_normalize = MagicMock(return_value=["（2025）粤01民初1号"])
        with patch("apps.core.llm.config.LLMConfig.get_ollama_model", return_value="model"):
            result = svc.extract_from_content("content")
        assert len(result) > 0

    def test_llm_empty_response(self):
        llm = MagicMock()
        llm.chat.return_value = MagicMock(content="")
        svc = self._svc(llm_service=llm)
        with patch("apps.core.llm.config.LLMConfig.get_ollama_model", return_value="model"):
            result = svc.extract_from_content("content")
        assert result == []

    def test_llm_error(self):
        from apps.core.llm.exceptions import LLMError
        llm = MagicMock()
        llm.chat.side_effect = LLMError("fail")
        svc = self._svc(llm_service=llm)
        with patch("apps.core.llm.config.LLMConfig.get_ollama_model", return_value="model"):
            result = svc.extract_from_content("content")
        assert result == []

    def test_llm_generic_error(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("boom")
        svc = self._svc(llm_service=llm)
        with patch("apps.core.llm.config.LLMConfig.get_ollama_model", return_value="model"):
            result = svc.extract_from_content("content")
        assert result == []


# ---------------------------------------------------------------------------
# _build_extract_prompt
# ---------------------------------------------------------------------------


class TestBuildExtractPrompt:
    def test_contains_content(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        prompt = svc._build_extract_prompt("文书内容")
        assert "文书内容" in prompt
        assert "案号" in prompt

    def test_json_format_instructions(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        prompt = svc._build_extract_prompt("内容")
        assert "case_numbers" in prompt


# ---------------------------------------------------------------------------
# _parse_ollama_response
# ---------------------------------------------------------------------------


class TestParseOllamaResponse:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_valid_json(self):
        svc = self._svc()
        svc.validate_and_normalize = MagicMock(return_value=["（2025）粤01民初1号"])
        result = svc._parse_ollama_response('{"case_numbers": ["（2025）粤01民初1号"]}')
        assert result == ["（2025）粤01民初1号"]

    def test_json_embedded_in_text(self):
        svc = self._svc()
        svc.validate_and_normalize = MagicMock(return_value=["（2025）粤01民初1号"])
        result = svc._parse_ollama_response('Here is the result: {"case_numbers": ["（2025）粤01民初1号"]} done.')
        assert result == ["（2025）粤01民初1号"]

    def test_invalid_json_falls_back(self):
        svc = self._svc()
        svc._extract_fallback = MagicMock(return_value=["fallback"])
        result = svc._parse_ollama_response("not json at all")
        assert result == ["fallback"]

    def test_json_no_case_numbers_key(self):
        svc = self._svc()
        svc._extract_fallback = MagicMock(return_value=[])
        result = svc._parse_ollama_response('{"other": "data"}')
        assert result == []

    def test_case_numbers_not_list(self):
        svc = self._svc()
        svc._extract_fallback = MagicMock(return_value=[])
        result = svc._parse_ollama_response('{"case_numbers": "not a list"}')
        assert result == []

    def test_no_braces(self):
        svc = self._svc()
        svc._extract_fallback = MagicMock(return_value=[])
        result = svc._parse_ollama_response("no json here")
        assert result == []


# ---------------------------------------------------------------------------
# validate_and_normalize
# ---------------------------------------------------------------------------


class TestValidateAndNormalize:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_empty(self):
        svc = self._svc()
        assert svc.validate_and_normalize([]) == []

    def test_valid_numbers(self):
        svc = self._svc()
        svc._normalize_single = MagicMock(return_value="（2025）粤01民初1号")
        result = svc.validate_and_normalize(["（2025）粤01民初1号"])
        assert result == ["（2025）粤01民初1号"]

    def test_dedup(self):
        svc = self._svc()
        svc._normalize_single = MagicMock(return_value="（2025）粤01民初1号")
        result = svc.validate_and_normalize(["（2025）粤01民初1号", "（2025）粤01民初1号"])
        assert result == ["（2025）粤01民初1号"]

    def test_invalid_skipped(self):
        svc = self._svc()
        svc._normalize_single = MagicMock(return_value=None)
        result = svc.validate_and_normalize(["invalid"])
        assert result == []

    def test_exception_returns_empty(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.side_effect = RuntimeError("boom")
        svc._case_number_service = cn_svc
        # validate_and_normalize catches exceptions
        result = svc.validate_and_normalize(["test"])
        assert result == []


# ---------------------------------------------------------------------------
# _normalize_single
# ---------------------------------------------------------------------------


class TestNormalizeSingle:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_valid_standard_format(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        result = svc._normalize_single("（2025）粤01民初1号", 0, cn_svc)
        assert result == "（2025）粤01民初1号"

    def test_empty_input(self):
        svc = self._svc()
        cn_svc = MagicMock()
        assert svc._normalize_single("", 0, cn_svc) is None

    def test_none_input(self):
        svc = self._svc()
        cn_svc = MagicMock()
        assert svc._normalize_single(None, 0, cn_svc) is None

    def test_not_string(self):
        svc = self._svc()
        cn_svc = MagicMock()
        assert svc._normalize_single(123, 0, cn_svc) is None

    def test_normalize_returns_empty(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = ""
        assert svc._normalize_single("test", 0, cn_svc) is None

    def test_normalize_raises(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.side_effect = RuntimeError("boom")
        assert svc._normalize_single("test", 0, cn_svc) is None

    def test_format_mismatch(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "not-a-case-number"
        assert svc._normalize_single("test", 0, cn_svc) is None

    def test_standard_pattern(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初12345号"
        result = svc._normalize_single("（2025）粤01民初12345号", 0, cn_svc)
        assert result == "（2025）粤01民初12345号"

    def test_simple_pattern(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "粤01民初12345号"
        result = svc._normalize_single("粤01民初12345号", 0, cn_svc)
        assert result == "粤01民初12345号"


# ---------------------------------------------------------------------------
# sync_to_case
# ---------------------------------------------------------------------------


class TestSyncToCase:
    def _svc(self, **kw):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService(**kw)

    def test_empty_case_id(self):
        svc = self._svc()
        assert svc.sync_to_case(0, ["123"], 1) == 0

    def test_empty_numbers(self):
        svc = self._svc()
        assert svc.sync_to_case(1, [], 1) == 0

    def test_dedup_returns_empty(self):
        svc = self._svc()
        svc._deduplicate = MagicMock(return_value=[])
        assert svc.sync_to_case(1, ["dup"], 1) == 0

    def test_existing_numbers_returns_none(self):
        svc = self._svc()
        svc._deduplicate = MagicMock(return_value=["（2025）粤01民初1号"])
        svc._get_existing_numbers = MagicMock(return_value=None)
        assert svc.sync_to_case(1, ["（2025）粤01民初1号"], 1) == 0

    def test_successful_sync(self):
        svc = self._svc()
        svc._deduplicate = MagicMock(return_value=["（2025）粤01民初1号"])
        svc._get_existing_numbers = MagicMock(return_value=set())
        svc._write_new_numbers = MagicMock(return_value=1)
        result = svc.sync_to_case(1, ["（2025）粤01民初1号"], 1)
        assert result == 1

    def test_exception_returns_zero(self):
        svc = self._svc()
        svc._deduplicate = MagicMock(side_effect=RuntimeError("boom"))
        assert svc.sync_to_case(1, ["123"], 1) == 0


# ---------------------------------------------------------------------------
# _get_existing_numbers
# ---------------------------------------------------------------------------


class TestGetExistingNumbers:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_success(self):
        svc = self._svc()
        svc._case_service = MagicMock()
        svc._case_service.get_case_numbers_by_case_internal.return_value = ["（2025）粤01民初1号"]
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        result = svc._get_existing_numbers(1, cn_svc)
        assert "（2025）粤01民初1号" in result

    def test_exception_returns_none(self):
        svc = self._svc()
        svc._case_service = MagicMock()
        svc._case_service.get_case_numbers_by_case_internal.side_effect = RuntimeError("boom")
        cn_svc = MagicMock()
        result = svc._get_existing_numbers(1, cn_svc)
        assert result is None

    def test_empty_normalize_skipped(self):
        svc = self._svc()
        svc._case_service = MagicMock()
        svc._case_service.get_case_numbers_by_case_internal.return_value = ["bad"]
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = ""
        result = svc._get_existing_numbers(1, cn_svc)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _write_new_numbers
# ---------------------------------------------------------------------------


class TestWriteNewNumbers:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_writes_new(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        cn_svc.create_number.return_value = MagicMock()
        result = svc._write_new_numbers(1, ["（2025）粤01民初1号"], set(), 1, cn_svc)
        assert result == 1
        cn_svc.create_number.assert_called_once()

    def test_skips_existing(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        result = svc._write_new_numbers(1, ["（2025）粤01民初1号"], {"（2025）粤01民初1号"}, 1, cn_svc)
        assert result == 0

    def test_normalize_returns_empty(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = ""
        result = svc._write_new_numbers(1, ["bad"], set(), 1, cn_svc)
        assert result == 0

    def test_create_raises(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        cn_svc.create_number.side_effect = RuntimeError("boom")
        result = svc._write_new_numbers(1, ["（2025）粤01民初1号"], set(), 1, cn_svc)
        assert result == 0


# ---------------------------------------------------------------------------
# _extract_fallback
# ---------------------------------------------------------------------------


class TestExtractFallback:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_empty(self):
        svc = self._svc()
        assert svc._extract_fallback("") == []

    def test_whitespace(self):
        svc = self._svc()
        assert svc._extract_fallback("   ") == []

    def test_finds_numbers(self):
        svc = self._svc()
        svc._regex_extract_numbers = MagicMock(return_value=["（2025）粤01民初1号"])
        svc.validate_and_normalize = MagicMock(return_value=["（2025）粤01民初1号"])
        result = svc._extract_fallback("some text with （2025）粤01民初1号")
        assert result == ["（2025）粤01民初1号"]

    def test_no_numbers(self):
        svc = self._svc()
        svc._regex_extract_numbers = MagicMock(return_value=[])
        svc.validate_and_normalize = MagicMock(return_value=[])
        result = svc._extract_fallback("no case numbers here")
        assert result == []

    def test_exception_returns_empty(self):
        svc = self._svc()
        svc._regex_extract_numbers = MagicMock(side_effect=RuntimeError("boom"))
        result = svc._extract_fallback("text")
        assert result == []


# ---------------------------------------------------------------------------
# _regex_extract_numbers
# ---------------------------------------------------------------------------


class TestRegexExtractNumbers:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_standard_format(self):
        svc = self._svc()
        result = svc._regex_extract_numbers("（2025）粤01民初12345号")
        assert len(result) > 0

    def test_no_match(self):
        svc = self._svc()
        result = svc._regex_extract_numbers("no numbers here")
        assert isinstance(result, list)

    def test_multiple_formats(self):
        svc = self._svc()
        result = svc._regex_extract_numbers("(2025)粤01民初123号 粤02民终456号")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def _svc(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        return CaseNumberExtractorService()

    def test_empty(self):
        svc = self._svc()
        assert svc._deduplicate([]) == []

    def test_dedup(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        svc._case_number_service = cn_svc
        result = svc._deduplicate(["（2025）粤01民初1号", "（2025）粤01民初1号"])
        assert result == ["（2025）粤01民初1号"]

    def test_none_values_skipped(self):
        svc = self._svc()
        cn_svc = MagicMock()
        cn_svc.normalize_case_number.return_value = "（2025）粤01民初1号"
        svc._case_number_service = cn_svc
        result = svc._deduplicate([None, "（2025）粤01民初1号", ""])
        assert result == ["（2025）粤01民初1号"]

    def test_exception_returns_original(self):
        svc = self._svc()
        svc._case_number_service = MagicMock()
        svc._case_number_service.normalize_case_number.side_effect = RuntimeError("boom")
        result = svc._deduplicate(["123"])
        assert result == ["123"]


# ---------------------------------------------------------------------------
# Lazy properties
# ---------------------------------------------------------------------------


class TestLazyProperties:
    def test_document_processing_service_lazy(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        svc._document_processing_service = None
        with patch("apps.core.dependencies.automation_sms_wiring.build_sms_document_processing_service", return_value="dps"):
            assert svc.document_processing_service == "dps"

    def test_case_service_lazy(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        svc._case_service = None
        with patch("apps.core.dependencies.automation_sms_wiring.build_sms_case_service", return_value="cs"):
            assert svc.case_service == "cs"

    def test_case_number_service_lazy(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        svc._case_number_service = None
        with patch("apps.core.dependencies.automation_sms_wiring.build_sms_case_number_service", return_value="cns"):
            assert svc.case_number_service == "cns"

    def test_llm_service_lazy(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
        svc = CaseNumberExtractorService()
        svc._llm_service = None
        with patch("apps.core.interfaces.ServiceLocator.get_llm_service", return_value="llm"):
            assert svc.llm_service == "llm"
