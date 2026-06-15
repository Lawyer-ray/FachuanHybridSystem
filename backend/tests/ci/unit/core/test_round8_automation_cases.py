"""Tests for automation_sms_wiring, court_token_store, task_lifecycle, case_command_service, and other modules."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.dependencies.automation_sms_wiring import (
    build_court_sms_service_with_deps,
    build_sms_case_service,
    build_sms_client_service,
    build_sms_lawyer_service,
    build_sms_case_chat_service,
    build_sms_case_log_service,
    build_sms_document_processing_service,
    build_sms_case_number_service,
)
from apps.core.tasking.submission import TaskSubmissionService
from apps.automation.services.token.court_token_store_service import CourtTokenStoreService
from apps.core.tasking.context import TaskContext
from apps.cases.services.case.case_command_service import CaseCommandService
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector


# ---------------------------------------------------------------------------
# automation_sms_wiring
# ---------------------------------------------------------------------------


class TestAutomationSmsWiring:
    def test_build_court_sms_service(self):
        result = build_court_sms_service_with_deps(
            case_service=MagicMock(),
            document_processing_service=MagicMock(),
            case_number_service=MagicMock(),
            client_service=MagicMock(),
            lawyer_service=MagicMock(),
            case_chat_service=MagicMock(),
            caselog_service=MagicMock(),
            reminder_service=MagicMock(),
        )
        assert result is not None

    def test_build_sms_case_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_case_service.return_value = MagicMock()
            result = build_sms_case_service()
            assert result is not None

    def test_build_sms_client_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_client_service.return_value = MagicMock()
            result = build_sms_client_service()
            assert result is not None

    def test_build_sms_lawyer_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_lawyer_service.return_value = MagicMock()
            result = build_sms_lawyer_service()
            assert result is not None

    def test_build_sms_case_chat_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_case_chat_service.return_value = MagicMock()
            result = build_sms_case_chat_service()
            assert result is not None

    def test_build_sms_case_log_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_caselog_service.return_value = MagicMock()
            result = build_sms_case_log_service()
            assert result is not None

    def test_build_sms_document_processing_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_document_processing_service.return_value = MagicMock()
            result = build_sms_document_processing_service()
            assert result is not None

    def test_build_sms_case_number_service(self):
        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            mock_sl.get_case_number_service.return_value = MagicMock()
            result = build_sms_case_number_service()
            assert result is not None


# ---------------------------------------------------------------------------
# TaskContext and TaskSubmissionService
# ---------------------------------------------------------------------------


class TestTaskContext:
    def test_default_context(self):
        ctx = TaskContext()
        assert ctx.request_id is None
        assert ctx.task_name is None

    def test_to_dict(self):
        ctx = TaskContext(request_id="req1", task_name="task1")
        d = ctx.to_dict()
        assert d["request_id"] == "req1"
        assert d["task_name"] == "task1"

    def test_from_dict(self):
        d = {"request_id": "req1", "task_name": "task1", "metadata": {}}
        ctx = TaskContext.from_dict(d)
        assert ctx.request_id == "req1"


# ---------------------------------------------------------------------------
# CaseCommandService
# ---------------------------------------------------------------------------


class TestCaseCommandService:
    def test_validate_stage_valid(self):
        svc = CaseCommandService(contract_service=MagicMock())
        result = svc._validate_stage("litigation", None, None)
        assert result == "litigation"

    def test_validate_stage_invalid_case_type(self):
        with patch("apps.cases.services.case.case_command_service.business_config") as mock_config:
            mock_config.is_stage_valid_for_case_type.return_value = False
            svc = CaseCommandService(contract_service=MagicMock())
            with pytest.raises(Exception):
                svc._validate_stage("stage", "type", None)

    def test_validate_stage_invalid_rep_stages(self):
        svc = CaseCommandService(contract_service=MagicMock())
        with pytest.raises(Exception):
            svc._validate_stage("bad_stage", None, ["stage1", "stage2"])

    def test_validate_contract_no_service(self):
        svc = CaseCommandService(contract_service=None)
        svc._validate_contract(1)  # Should not raise

    def test_validate_contract_not_found(self):
        mock_cs = MagicMock()
        mock_cs.get_contract.return_value = None
        svc = CaseCommandService(contract_service=mock_cs)
        with pytest.raises(Exception):
            svc._validate_contract(999)

    def test_validate_contract_inactive(self):
        mock_cs = MagicMock()
        mock_cs.get_contract.return_value = MagicMock()
        mock_cs.validate_contract_active.return_value = False
        svc = CaseCommandService(contract_service=mock_cs)
        with pytest.raises(Exception):
            svc._validate_contract(1)

    def test_resolve_stage_from_contract_no_contract(self):
        svc = CaseCommandService(contract_service=None)
        result = svc._resolve_stage_from_contract(None, "litigation")
        assert result == "litigation"

    def test_resolve_stage_from_contract_with_contract(self):
        mock_cs = MagicMock()
        mock_contract = MagicMock()
        mock_contract.case_type = "civil"
        mock_contract.representation_stages = ["litigation", "execution"]
        mock_cs.get_contract.return_value = mock_contract
        svc = CaseCommandService(contract_service=mock_cs)
        with patch("apps.cases.services.case.case_command_service.business_config") as mock_config:
            mock_config.is_stage_valid_for_case_type.return_value = True
            result = svc._resolve_stage_from_contract(1, "litigation")
            assert result == "litigation"

    def test_close_cases_by_contract_internal(self):
        with patch("apps.cases.services.case.case_command_service.Case") as MockCase:
            MockCase.objects.filter.return_value.update.return_value = 2
            svc = CaseCommandService()
            count = svc.close_cases_by_contract_internal(1)
            assert count == 2

    def test_close_cases_by_contract_internal_zero(self):
        with patch("apps.cases.services.case.case_command_service.Case") as MockCase:
            MockCase.objects.filter.return_value.update.return_value = 0
            svc = CaseCommandService()
            count = svc.close_cases_by_contract_internal(1)
            assert count == 0


# ---------------------------------------------------------------------------
# CourtTokenStoreService
# ---------------------------------------------------------------------------


class TestCourtTokenStoreService:
    def test_get_latest_valid_token_internal_none(self):
        svc = CourtTokenStoreService()
        with patch("apps.automation.models.CourtToken") as MockToken:
            MockToken.objects.filter.return_value.order_by.return_value.first.return_value = None
            result = svc.get_latest_valid_token_internal(site_name="test")
            assert result is None

    def test_save_token_internal(self):
        svc = CourtTokenStoreService()
        with patch("apps.automation.models.CourtToken") as MockToken:
            svc.save_token_internal(
                site_name="test",
                account="user@test.com",
                token="abc123",
                expires_in=3600,
            )
            MockToken.objects.update_or_create.assert_called_once()


# ---------------------------------------------------------------------------
# SegmentDetector basic methods
# ---------------------------------------------------------------------------


class TestSegmentDetector:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_normalize_text(self):
        assert self.detector.normalize_text("Hello World 123") == "HelloWorld123"

    def test_contains_keyword(self):
        assert self.detector.contains_keyword("Hello World", "World") is True
        assert self.detector.contains_keyword("Hello World", "xyz") is False

    def test_is_effective_text_long(self):
        assert self.detector.is_effective_text("a" * 20) is True

    def test_is_effective_text_short(self):
        assert self.detector.is_effective_text("ab") is False

    def test_fuzzy_contains_exact(self):
        hit, decay = self.detector.fuzzy_contains_keyword("Hello World", "World")
        assert hit is True
        assert decay == 1.0

    def test_fuzzy_contains_no_match(self):
        hit, decay = self.detector.fuzzy_contains_keyword("Hello World", "xyz")
        assert hit is False
        assert decay == 0.0

    def test_fuzzy_contains_empty_keyword(self):
        hit, decay = self.detector.fuzzy_contains_keyword("Hello World", "")
        assert hit is False

    def test_fuzzy_contains_short_keyword_no_match(self):
        hit, decay = self.detector.fuzzy_contains_keyword("abcdef", "xyz")
        assert hit is False

    def test_fill_unrecognized_gaps(self):
        from apps.pdf_splitting.models import PdfSplitSegmentType, PdfSplitReviewFlag
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        segments = [
            SegmentDraft(
                order=1,
                page_start=3,
                page_end=5,
                segment_type=PdfSplitSegmentType.COMPLAINT,
                filename="test.pdf",
                confidence=0.9,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            )
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) >= 2  # gap before + segment + gap after
        assert result[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert result[0].page_start == 1
        assert result[0].page_end == 2

    def test_merge_adjacent_pack_segments_empty(self):
        assert self.detector._merge_adjacent_pack_segments([]) == []


# ---------------------------------------------------------------------------
# JudgmentPdfExtractor
# ---------------------------------------------------------------------------


class TestJudgmentPdfExtractor:
    def setup_method(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor
        self.extractor = JudgmentPdfExtractor()

    def test_extract_case_number(self):
        text = "（2024）粤0605民初3356号"
        result = self.extractor._extract_case_number(text)
        assert result is not None
        assert "粤0605" in result

    def test_extract_case_number_near_keyword(self):
        text = "案号：（2024）粤0605民初3356号"
        result = self.extractor._extract_case_number(text)
        assert result is not None

    def test_extract_case_number_none(self):
        result = self.extractor._extract_case_number("no case number here")
        assert result is None

    def test_extract_document_name(self):
        text = "某某人民法院民事判决书"
        result = self.extractor._extract_document_name(text)
        assert result == "民事判决书"

    def test_extract_document_name_none(self):
        result = self.extractor._extract_document_name("no document name")
        assert result is None

    def test_extract_main_text(self):
        text = "经审理，判决如下：一、被告赔偿原告10000元。如不服本判决，可以上诉。"
        result = self.extractor._extract_main_text(text)
        assert result is not None
        assert "被告赔偿原告" in result

    def test_extract_main_text_none(self):
        result = self.extractor._extract_main_text("no judgment keywords here")
        assert result is None

    def test_sanitize_extracted_text(self):
        text = "Hello\n\n\nWorld\r\nTest"
        result = self.extractor._sanitize_extracted_text(text)
        assert "\r" not in result
        assert "Hello" in result
        assert "World" in result

    def test_sanitize_extracted_text_empty(self):
        assert self.extractor._sanitize_extracted_text(None) == ""
        assert self.extractor._sanitize_extracted_text("") == ""

    def test_sanitize_page_noise(self):
        text = "Main content 第1页/共10页 Footer"
        result = self.extractor._sanitize_extracted_text(text)
        assert "第1页" not in result

    def test_map_normalized_to_original(self):
        original = "Hello World"
        # normalized = "HelloWorld" (no space), index 5 = "W" in normalized -> position 6 in original
        result = self.extractor._map_normalized_to_original(original, 5)
        assert original[result] == "W"

    def test_extract_with_ollama_unavailable(self):
        with patch("apps.core.llm.backends.ollama.OllamaBackend") as MockBackend:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = False
            MockBackend.return_value = mock_instance
            result = self.extractor._extract_with_ollama("some text")
            assert result is None

    def test_end_keywords(self):
        assert len(self.extractor.END_KEYWORDS) > 0
        assert "审判长" in self.extractor.END_KEYWORDS

    def test_document_name_keywords(self):
        assert "民事判决书" in self.extractor.DOCUMENT_NAME_KEYWORDS
        assert "执行证书" in self.extractor.DOCUMENT_NAME_KEYWORDS
