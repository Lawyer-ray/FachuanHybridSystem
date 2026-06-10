"""Coverage tests for SMS services and matching stage.

Targets uncovered lines in:
- sms/case_matcher.py (65 uncovered)
- sms/case_number_extractor_service.py (61 uncovered)
- sms/court_sms_recommendation_service.py (69 uncovered)
- sms/stages/sms_matching_stage.py (56 uncovered)
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers


# ===================================================================
# filter_valid_case_numbers (pure function)
# ===================================================================
class TestFilterValidCaseNumbers:
    def test_empty_list(self):
        assert filter_valid_case_numbers([]) == []

    def test_valid_case_numbers(self):
        nums = ["(2024)粤01民初1号", "(2023)粤01执123号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 2

    def test_filters_date_format(self):
        nums = ["2024年1月15日", "(2024)粤01民初1号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 1
        assert "(2024)粤01民初1号" in result

    def test_filters_year_month_day_number(self):
        nums = ["2024年1月15号", "(2024)粤01民初1号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 1

    def test_keeps_valid_numbers(self):
        nums = ["粤0604民初12345号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 1


# ===================================================================
# CourtSMSRecommendationService (mocked DB)
# ===================================================================
class TestCourtSMSRecommendationService:
    def test_collect_year_court_prefixes(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._collect_year_court_prefixes(["(2024)粤01民初1号", "(2023)京0101刑初100号"])
        assert "(2024)粤01" in result
        assert "(2023)京0101" in result

    def test_collect_year_court_prefixes_empty(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._collect_year_court_prefixes([])
        assert result == []

    def test_collect_year_court_prefixes_no_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._collect_year_court_prefixes(["no_match_here"])
        assert result == []

    def test_extract_court_name_from_content(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._extract_court_name_from_content("广州市天河区人民法院通知您")
        assert result == "广州市天河区人民法院"

    def test_extract_court_name_from_content_no_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._extract_court_name_from_content("普通短信内容")
        assert result is None

    def test_extract_court_name_from_content_empty(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        result = svc._extract_court_name_from_content("")
        assert result is None

    def test_build_query_all_empty(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query([], [], None, [])
        assert result is None

    def test_build_query_with_numbers(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query(
            ["(2024)粤01民初1号"], [], None, []
        )
        assert result is not None

    def test_build_query_with_court_name(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query(
            [], [], "天河区人民法院", []
        )
        assert result is not None

    def test_build_query_with_parties(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query([], [], None, ["张三"])
        assert result is not None

    def test_build_query_short_party_name_skipped(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query([], [], None, ["张"])
        assert result is None

    def test_build_query_with_prefixes(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        result = CourtSMSRecommendationService._build_query([], ["(2024)粤01"], None, [])
        assert result is not None

    def test_extract_court_name_from_document_no_task(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        sms = SimpleNamespace(scraper_task=None)
        result = svc._extract_court_name_from_document(sms)
        assert result is None

    def test_extract_court_name_from_document_no_documents(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        task = SimpleNamespace(documents=None)
        sms = SimpleNamespace(scraper_task=task)
        result = svc._extract_court_name_from_document(sms)
        assert result is None

    def test_extract_court_name_from_document_exception(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        sms = SimpleNamespace()  # no scraper_task attr
        result = svc._extract_court_name_from_document(sms)
        assert result is None

    def test_extract_court_name_fallback_to_content(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        sms = SimpleNamespace(
            scraper_task=None,
            content="北京市朝阳区人民法院通知",
        )
        result = svc._extract_court_name(sms)
        assert result == "北京市朝阳区人民法院"

    def test_extract_court_name_returns_none(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        sms = SimpleNamespace(scraper_task=None, content="普通短信")
        result = svc._extract_court_name(sms)
        assert result is None


# ===================================================================
# RecommendationResult dataclass
# ===================================================================
class TestRecommendationResult:
    def test_defaults(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            RecommendationResult,
        )

        r = RecommendationResult(case_id=1, case_name="Test", score=100)
        assert r.reasons == []
        assert r.case_numbers == []
        assert r.parties == []
        assert r.court_names == []
        assert r.status == ""

    def test_with_values(self):
        from apps.automation.services.sms.court_sms_recommendation_service import (
            RecommendationResult,
        )

        r = RecommendationResult(
            case_id=1,
            case_name="Test Case",
            score=150,
            reasons=["案号完全匹配"],
            case_numbers=["(2024)粤01民初1号"],
            parties=["张三", "李四"],
            court_names=["天河区人民法院"],
            status="active",
        )
        assert r.score == 150
        assert len(r.reasons) == 1


# ===================================================================
# CaseNumberExtractorService (with mocks)
# ===================================================================
class TestCaseNumberExtractorService:
    def test_empty_document_path(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        result = svc.extract_from_document("")
        assert result == []

    def test_extract_from_document_success(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.return_value = {
            "text": "案号(2024)粤01民初1号"
        }
        svc = CaseNumberExtractorService(
            document_processing_service=doc_service,
            extraction_provider=Mock(extract=Mock(return_value='{"case_numbers": ["(2024)粤01民初1号"]}')),
            case_number_service=Mock(normalize_case_number=Mock(return_value="(2024)粤01民初1号")),
        )
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert len(result) > 0

    def test_extract_from_document_no_text(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.return_value = {"text": ""}
        svc = CaseNumberExtractorService(document_processing_service=doc_service)
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_extract_from_document_none_result(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.return_value = None
        svc = CaseNumberExtractorService(document_processing_service=doc_service)
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_extract_from_document_file_not_found(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.side_effect = FileNotFoundError
        svc = CaseNumberExtractorService(document_processing_service=doc_service)
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_extract_from_document_connection_error(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.side_effect = ConnectionError
        svc = CaseNumberExtractorService(document_processing_service=doc_service)
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_extract_from_document_generic_exception(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        doc_service = Mock()
        doc_service.extract_document_content_by_path_internal.side_effect = RuntimeError
        svc = CaseNumberExtractorService(document_processing_service=doc_service)
        result = svc.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_parse_ollama_response_valid_json(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService(
            case_number_service=Mock(normalize_case_number=Mock(return_value="(2024)粤01民初1号"))
        )
        result = svc._parse_ollama_response('{"case_numbers": ["(2024)粤01民初1号"]}')
        assert len(result) == 1

    def test_parse_ollama_response_invalid_json(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        with patch.object(svc, "_extract_fallback", return_value=[]):
            result = svc._parse_ollama_response("not json")
        assert result == []

    def test_parse_ollama_response_no_case_numbers_key(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        with patch.object(svc, "_extract_fallback", return_value=[]):
            result = svc._parse_ollama_response('{"other_key": "value"}')
        assert result == []

    def test_validate_and_normalize_empty(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        result = svc.validate_and_normalize([])
        assert result == []

    def test_validate_and_normalize_with_valid(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        case_number_svc = Mock()
        case_number_svc.normalize_case_number.return_value = "(2024)粤01民初1号"
        svc = CaseNumberExtractorService(case_number_service=case_number_svc)
        result = svc.validate_and_normalize(["(2024)粤01民初1号"])
        assert len(result) == 1

    def test_validate_and_normalize_dedup(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        case_number_svc = Mock()
        case_number_svc.normalize_case_number.return_value = "(2024)粤01民初1号"
        svc = CaseNumberExtractorService(case_number_service=case_number_svc)
        result = svc.validate_and_normalize(["(2024)粤01民初1号", "(2024)粤01民初1号"])
        assert len(result) == 1

    def test_validate_and_normalize_exception(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService(case_number_service=None)
        # Manually set case_number_service to avoid lazy loading
        svc._case_number_service = Mock(normalize_case_number=Mock(side_effect=RuntimeError))
        result = svc.validate_and_normalize(["test"])
        assert result == []

    def test_build_extract_prompt(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        prompt = svc._build_extract_prompt("test content")
        assert "test content" in prompt
        assert "案号" in prompt

    def test_normalize_single_empty(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        result = svc._normalize_single("", 0, Mock())
        assert result is None

    def test_normalize_single_non_string(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        result = svc._normalize_single(None, 0, Mock())
        assert result is None

    def test_normalize_single_normalization_fails(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        cn_svc = Mock()
        cn_svc.normalize_case_number.return_value = ""
        result = svc._normalize_single("test", 0, cn_svc)
        assert result is None

    def test_normalize_single_normalization_exception(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        cn_svc = Mock()
        cn_svc.normalize_case_number.side_effect = RuntimeError
        result = svc._normalize_single("test", 0, cn_svc)
        assert result is None

    def test_normalize_single_invalid_format(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        cn_svc = Mock()
        cn_svc.normalize_case_number.return_value = "not_a_case_number"
        result = svc._normalize_single("test", 0, cn_svc)
        assert result is None


# ===================================================================
# CaseMatcher (with mocks)
# ===================================================================
class TestCaseMatcher:
    def test_match_no_case_numbers_no_parties(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        doc_parser = Mock()
        doc_parser.get_all_document_paths.return_value = []
        party_matching = Mock()
        case_service = Mock()

        sms = SimpleNamespace(case_numbers=[], party_names=[])
        matcher = CaseMatcher(
            case_service=case_service,
            document_parser_service=doc_parser,
            party_matching_service=party_matching,
        )
        result = matcher.match(sms)
        assert result is None

    def test_match_exception_raises_validation(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.exceptions import ValidationException

        doc_parser = Mock()
        doc_parser.get_all_document_paths.return_value = []
        party_matching = Mock()
        case_service = Mock()

        sms = SimpleNamespace(case_numbers=[], party_names=["张三", "李四"])
        matcher = CaseMatcher(
            case_service=case_service,
            document_parser_service=doc_parser,
            party_matching_service=party_matching,
        )
        # Make _match_by_party_names_all raise
        matcher._match_by_party_names_all = Mock(side_effect=RuntimeError("DB error"))
        with pytest.raises(ValidationException):
            matcher.match(sms)

    def test_extract_party_names_from_sms(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        doc_parser = Mock()
        matcher = CaseMatcher(document_parser_service=doc_parser)
        sms = SimpleNamespace(party_names=["张三", "李四"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_single_then_doc(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        doc_parser = Mock()
        doc_parser.get_all_document_paths.return_value = ["/path/doc.pdf"]
        doc_parser.extract_parties_from_document.return_value = ["张三", "李四"]
        matcher = CaseMatcher(document_parser_service=doc_parser)
        sms = SimpleNamespace(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_doc_failure_fallback_sms(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        doc_parser = Mock()
        doc_parser.get_all_document_paths.return_value = ["/path/doc.pdf"]
        doc_parser.extract_parties_from_document.side_effect = RuntimeError
        matcher = CaseMatcher(document_parser_service=doc_parser)
        sms = SimpleNamespace(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_extract_party_names_no_docs_no_sms(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        doc_parser = Mock()
        doc_parser.get_all_document_paths.return_value = []
        matcher = CaseMatcher(document_parser_service=doc_parser)
        sms = SimpleNamespace(party_names=[])
        result = matcher._extract_party_names(sms)
        assert result == []

    def test_match_by_party_names_all_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(party_matching_service=Mock())
        result = matcher._match_by_party_names_all([])
        assert result == []

    def test_extract_features_from_numbers(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        case_type, stage, is_bankruptcy = matcher._extract_features_from_numbers(
            ["(2024)粤01民初1号"]
        )
        # Just testing it doesn't crash and returns tuple
        assert isinstance(case_type, (str, type(None)))
        assert isinstance(is_bankruptcy, bool)

    def test_narrow_down_empty_cases(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        result = matcher._narrow_down_by_case_number_features([], ["(2024)粤01民初1号"])
        assert result is None

    def test_narrow_down_empty_numbers(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        result = matcher._narrow_down_by_case_number_features([Mock()], [])
        assert result is None

    def test_filter_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = SimpleNamespace(name="某公司破产重整案")
        c2 = SimpleNamespace(name="普通民事案")
        result = matcher._filter_bankruptcy([c1, c2])
        assert c1 in result
        assert c2 not in result

    def test_filter_bankruptcy_fallback_to_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = SimpleNamespace(name="普通案")
        result = matcher._filter_bankruptcy([c1])
        assert c1 in result
