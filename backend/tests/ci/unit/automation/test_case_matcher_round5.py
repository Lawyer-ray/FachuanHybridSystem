"""case_matcher.py — round5 tests for uncovered branches.

Covers:
- match: exception wraps in ValidationException
- match: party_names single item falls back to document extraction
- _match_by_case_number_exact: single active match, single closed match
- _match_by_case_number_exact: multiple with one active
- _extract_party_names: sms has 2+ names, doc fails then sms fallback
- _narrow_down_by_case_number_features: no features returns None, type filter match
- _select_latest_case: empty list
- _detect_case_type_from_number: criminal, civil, administrative, bankruptcy
- _detect_case_stage_from_number: enforcement, second_trial, first_trial, no match
- match_by_party_names: no matches
- _find_all_matching_cases: bidirectional matching
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.enums import CaseStage, CaseStatus, CaseType


class _HelpersMixin:
    @staticmethod
    def _make_sms(case_numbers=None, party_names=None):
        sms = MagicMock()
        sms.case_numbers = case_numbers or []
        sms.party_names = party_names or []
        return sms

    @staticmethod
    def _make_case(case_id=1, name="TestCase", status=CaseStatus.ACTIVE,
                   case_type="civil", current_stage="first_trial"):
        case = MagicMock()
        case.id = case_id
        case.name = name
        case.status = status
        case.case_type = case_type
        case.current_stage = current_stage
        return case


# ── match — exception wrapping ────────────────────────────────────────────────


class TestMatchExceptionWrapping(_HelpersMixin):
    def test_wraps_in_validation_exception(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.exceptions import ValidationException

        matcher = CaseMatcher(case_service=MagicMock(), document_parser_service=MagicMock(), party_matching_service=MagicMock())
        # Patch internal methods to raise
        matcher._match_by_case_number_exact = MagicMock(side_effect=Exception("boom"))
        matcher._extract_party_names = MagicMock(return_value=[])
        matcher._check_and_log_closed_cases = MagicMock()
        sms = self._make_sms(case_numbers=["123"])
        with pytest.raises(ValidationException, match="案件匹配失败"):
            matcher.match(sms)


# ── _match_by_case_number_exact — single matches ─────────────────────────────


class TestMatchByCaseNumberExactSingle(_HelpersMixin):
    def test_single_active_returns_it(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        c = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c])
        result = matcher._match_by_case_number_exact(["123"])
        assert result == c

    def test_single_closed_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        c = self._make_case(case_id=1, status=CaseStatus.CLOSED)
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c])
        result = matcher._match_by_case_number_exact(["123"])
        assert result is None


# ── _match_by_case_number_exact — multiple with one active ───────────────────


class TestMatchByCaseNumberExactMultipleOneActive(_HelpersMixin):
    def test_returns_active(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        c1 = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        c2 = self._make_case(case_id=2, status=CaseStatus.CLOSED)
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c1, c2])
        result = matcher._match_by_case_number_exact(["123"])
        assert result == c1


# ── _match_by_case_number_exact — multiple active ────────────────────────────


class TestMatchByCaseNumberExactMultipleActive(_HelpersMixin):
    def test_returns_none_for_ambiguity(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        c1 = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        c2 = self._make_case(case_id=2, status=CaseStatus.ACTIVE)
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c1, c2])
        result = matcher._match_by_case_number_exact(["123"])
        assert result is None


# ── _extract_party_names ─────────────────────────────────────────────────────


class TestExtractPartyNamesBranches(_HelpersMixin):
    def test_sms_has_two_names(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(document_parser_service=MagicMock())
        sms = self._make_sms(party_names=["张三", "李四"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_sms_one_name_fallback_to_doc(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(document_parser_service=MagicMock())
        matcher.document_parser_service.get_all_document_paths.return_value = ["/doc.pdf"]
        matcher.document_parser_service.extract_parties_from_document.return_value = ["王五", "赵六"]
        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["王五", "赵六"]

    def test_doc_fails_sms_returns_single_name(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(document_parser_service=MagicMock())
        matcher.document_parser_service.get_all_document_paths.return_value = ["/doc.pdf"]
        matcher.document_parser_service.extract_parties_from_document.side_effect = Exception("fail")
        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_no_sms_no_doc_returns_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(document_parser_service=MagicMock())
        matcher.document_parser_service.get_all_document_paths.return_value = []
        sms = self._make_sms(party_names=[])
        result = matcher._extract_party_names(sms)
        assert result == []


# ── _narrow_down_by_case_number_features ─────────────────────────────────────


class TestNarrowDownFeatures(_HelpersMixin):
    def test_no_features_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c = self._make_case()
        result = matcher._narrow_down_by_case_number_features([c], ["（2025）粤01123号"])
        assert result is None

    def test_type_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = self._make_case(case_id=1, case_type="criminal")
        c2 = self._make_case(case_id=2, case_type="civil")
        result = matcher._narrow_down_by_case_number_features(
            [c1, c2], ["（2025）粤0605刑初123号"]
        )
        assert result == c1

    def test_type_filter_no_match_returns_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = self._make_case(case_id=1, case_type="civil", current_stage="enforcement")
        result = matcher._narrow_down_by_case_number_features(
            [c1], ["（2025）粤0605刑初123号"]
        )
        # Type filter returns no match, stage filter also returns no match (enforcement vs first_trial),
        # falls back to original list, len == 1 -> returns the single case
        assert result == c1

    def test_stage_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = self._make_case(case_id=1, current_stage="enforcement")
        result = matcher._narrow_down_by_case_number_features(
            [c1], ["（2025）粤0605执123号"]
        )
        assert result == c1


# ── _select_latest_case ──────────────────────────────────────────────────────


class TestSelectLatestCase(_HelpersMixin):
    def test_empty_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        assert CaseMatcher()._select_latest_case([]) is None

    def test_returns_highest_id(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=5)
        c3 = self._make_case(case_id=3)
        result = CaseMatcher()._select_latest_case([c1, c2, c3])
        assert result == c2


# ── _detect_case_type_from_number ────────────────────────────────────────────


class TestDetectCaseType(_HelpersMixin):
    def test_criminal(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("（2025）粤0605刑初123号") == CaseType.CRIMINAL

    def test_administrative(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("（2025）粤0605行初123号") == CaseType.ADMINISTRATIVE

    def test_civil(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("（2025）粤0605民初123号") == CaseType.CIVIL

    def test_bankruptcy_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("（2025）粤0605破123号") is None

    def test_empty_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("") is None

    def test_no_match_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_type_from_number("（2025）粤01执123号") is None


# ── _detect_case_stage_from_number ───────────────────────────────────────────


class TestDetectCaseStage(_HelpersMixin):
    def test_enforcement(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("（2025）粤0605执123号") == CaseStage.ENFORCEMENT

    def test_second_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("（2025）粤0605民终123号") == CaseStage.SECOND_TRIAL

    def test_first_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("（2025）粤0605民初123号") == CaseStage.FIRST_TRIAL

    def test_zhibao_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("（2025）粤0605执保123号") is None

    def test_empty_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("") is None

    def test_no_match_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("（2025）粤0605破123号") is None


# ── match_by_party_names ─────────────────────────────────────────────────────


class TestMatchByPartyNames(_HelpersMixin):
    def test_no_matches(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        matcher._match_by_party_names_all = MagicMock(return_value=[])
        assert matcher.match_by_party_names(["张三"]) is None


# ── _find_all_matching_cases — bidirectional matching ────────────────────────


class TestFindAllMatchingCases(_HelpersMixin):
    def test_bidirectional_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock())
        c1 = self._make_case(case_id=1)
        matcher.case_service.search_cases_by_party_internal.return_value = [c1]
        matcher.case_service.get_case_party_names_internal.return_value = ["张三", "李四"]

        client1 = MagicMock()
        client1.name = "张三"
        client2 = MagicMock()
        client2.name = "李四"

        result = matcher._find_all_matching_cases([client1, client2])
        assert len(result) == 1

    def test_partial_match_excluded(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock())
        c1 = self._make_case(case_id=1)
        matcher.case_service.search_cases_by_party_internal.return_value = [c1]
        matcher.case_service.get_case_party_names_internal.return_value = ["张三", "李四", "王五"]

        client1 = MagicMock()
        client1.name = "张三"

        result = matcher._find_all_matching_cases([client1])
        assert len(result) == 0  # Input doesn't cover all case parties


# ── _is_bankruptcy_case_number ───────────────────────────────────────────────


class TestIsBankruptcyCaseNumber:
    def test_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("") is False

    def test_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("（2025）破1号") is True

    def test_not_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("（2025）民初1号") is False


# ── _get_all_cases_by_numbers ────────────────────────────────────────────────


class TestGetAllCasesByNumbers(_HelpersMixin):
    def test_deduplicates(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock())
        c1 = self._make_case(case_id=1)
        matcher.case_service.search_cases_by_case_number_internal.return_value = [c1, c1]

        result = matcher._get_all_cases_by_numbers(["123"])
        assert len(result) == 1


# ── match_by_case_number ─────────────────────────────────────────────────────


class TestMatchByCaseNumberCompat(_HelpersMixin):
    def test_delegates_to_exact(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock())
        c = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c])
        result = matcher.match_by_case_number(["123"])
        assert result == c
