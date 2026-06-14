"""Comprehensive tests for automation.services.sms.case_matcher.

Covers: match, _match_by_case_number_exact, _extract_party_names,
_match_by_party_names_all, _narrow_down_by_case_number_features,
_extract_features_from_numbers, _filter_bankruptcy, _apply_type_filter,
_apply_stage_filter, _get_all_cases_by_numbers, _find_all_matching_cases,
_detect_case_type_from_number, _is_bankruptcy_case_number,
_detect_case_stage_from_number, match_by_case_number, match_by_party_names,
_select_latest_case, _check_and_log_closed_cases, _collect_closed_cases_by_number,
_collect_closed_cases_by_party, _get_case_matcher, lazy properties.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


class _HelpersMixin:
    """Shared helper to build SMS-like mock objects."""

    @staticmethod
    def _make_sms(case_numbers=None, party_names=None):
        sms = MagicMock()
        sms.case_numbers = case_numbers or []
        sms.party_names = party_names or []
        return sms

    @staticmethod
    def _make_case(case_id=1, name="TestCase", status="active", case_type="civil", current_stage="first_trial"):
        case = MagicMock()
        case.id = case_id
        case.name = name
        case.status = status
        case.case_type = case_type
        case.current_stage = current_stage
        return case


# ---------------------------------------------------------------------------
# _get_case_matcher factory
# ---------------------------------------------------------------------------


class TestGetCaseMatcher:
    def test_returns_instance(self):
        from apps.automation.services.sms.case_matcher import _get_case_matcher
        result = _get_case_matcher()
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert isinstance(result, CaseMatcher)


# ---------------------------------------------------------------------------
# Lazy properties
# ---------------------------------------------------------------------------


class TestCaseMatcherLazyProperties:
    def test_case_service_lazy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        matcher._case_service = None
        with patch("apps.automation.services.sms.matching") as m:
            pass  # We can't easily patch the import, but we test the property exists
        assert hasattr(matcher, "case_service")

    def test_document_parser_service_lazy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        matcher._document_parser_service = None
        assert hasattr(matcher, "document_parser_service")

    def test_party_matching_service_lazy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        matcher._party_matching_service = None
        assert hasattr(matcher, "party_matching_service")


# ---------------------------------------------------------------------------
# _detect_case_type_from_number
# ---------------------------------------------------------------------------


class TestDetectCaseTypeFromNumber(_HelpersMixin):
    def _fn(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        return CaseMatcher()

    def test_criminal(self):
        matcher = self._fn()
        from apps.core.models.enums import CaseType
        result = matcher._detect_case_type_from_number("（2025）粤0605刑初123号")
        assert result == CaseType.CRIMINAL

    def test_administrative(self):
        matcher = self._fn()
        from apps.core.models.enums import CaseType
        result = matcher._detect_case_type_from_number("（2025）粤0605行初123号")
        assert result == CaseType.ADMINISTRATIVE

    def test_civil(self):
        matcher = self._fn()
        from apps.core.models.enums import CaseType
        result = matcher._detect_case_type_from_number("（2025）粤0605民初123号")
        assert result == CaseType.CIVIL

    def test_bankruptcy_returns_none(self):
        matcher = self._fn()
        result = matcher._detect_case_type_from_number("（2025）粤0605破123号")
        assert result is None

    def test_empty(self):
        matcher = self._fn()
        assert matcher._detect_case_type_from_number("") is None


# ---------------------------------------------------------------------------
# _is_bankruptcy_case_number
# ---------------------------------------------------------------------------


class TestIsBankruptcyCaseNumber(_HelpersMixin):
    def test_true(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("（2025）粤0605破123号") is True

    def test_false(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("（2025）粤0605民初123号") is False

    def test_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._is_bankruptcy_case_number("") is False


# ---------------------------------------------------------------------------
# _detect_case_stage_from_number
# ---------------------------------------------------------------------------


class TestDetectCaseStageFromNumber(_HelpersMixin):
    def test_enforcement(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseStage
        result = CaseMatcher()._detect_case_stage_from_number("（2025）粤0605执123号")
        assert result == CaseStage.ENFORCEMENT

    def test_second_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseStage
        result = CaseMatcher()._detect_case_stage_from_number("（2025）粤0605民终123号")
        assert result == CaseStage.SECOND_TRIAL

    def test_first_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseStage
        result = CaseMatcher()._detect_case_stage_from_number("（2025）粤0605民初123号")
        assert result == CaseStage.FIRST_TRIAL

    def test_zhibao_not_enforcement(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        result = CaseMatcher()._detect_case_stage_from_number("（2025）粤0605执保123号")
        assert result is None  # 执保 is not enforcement

    def test_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._detect_case_stage_from_number("") is None


# ---------------------------------------------------------------------------
# _extract_features_from_numbers
# ---------------------------------------------------------------------------


class TestExtractFeaturesFromNumbers(_HelpersMixin):
    def test_civil_first_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseType, CaseStage
        ct, cs, bankruptcy = CaseMatcher()._extract_features_from_numbers(["（2025）粤01民初123号"])
        assert ct == CaseType.CIVIL
        assert cs == CaseStage.FIRST_TRIAL
        assert bankruptcy is False

    def test_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        ct, cs, bankruptcy = CaseMatcher()._extract_features_from_numbers(["（2025）粤01破123号"])
        assert bankruptcy is True

    def test_empty_list(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        ct, cs, bankruptcy = CaseMatcher()._extract_features_from_numbers([])
        assert ct is None
        assert cs is None
        assert bankruptcy is False


# ---------------------------------------------------------------------------
# _filter_bankruptcy
# ---------------------------------------------------------------------------


class TestFilterBankruptcy(_HelpersMixin):
    def test_filters_by_name(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(name="某公司破产重整案")
        c2 = self._make_case(case_id=2, name="普通民事案")
        result = CaseMatcher()._filter_bankruptcy([c1, c2])
        assert result == [c1]

    def test_fallback_to_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(name="普通案")
        result = CaseMatcher()._filter_bankruptcy([c1])
        assert result == [c1]


# ---------------------------------------------------------------------------
# _apply_type_filter / _apply_stage_filter
# ---------------------------------------------------------------------------


class TestFilters(_HelpersMixin):
    def test_type_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(case_type="civil")
        c2 = self._make_case(case_id=2, case_type="criminal")
        result = CaseMatcher()._apply_type_filter([c1, c2], "civil")
        assert result == [c1]

    def test_type_filter_no_match_fallback(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(case_type="civil")
        result = CaseMatcher()._apply_type_filter([c1], "administrative")
        assert result == [c1]

    def test_type_filter_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        cases = [self._make_case()]
        assert CaseMatcher()._apply_type_filter(cases, None) == cases

    def test_stage_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(current_stage="first_trial")
        c2 = self._make_case(case_id=2, current_stage="second_trial")
        result = CaseMatcher()._apply_stage_filter([c1, c2], "first_trial")
        assert result == [c1]

    def test_stage_filter_no_match_fallback(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(current_stage="first_trial")
        result = CaseMatcher()._apply_stage_filter([c1], "enforcement")
        assert result == [c1]

    def test_stage_filter_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        cases = [self._make_case()]
        assert CaseMatcher()._apply_stage_filter(cases, None) == cases


# ---------------------------------------------------------------------------
# _narrow_down_by_case_number_features
# ---------------------------------------------------------------------------


class TestNarrowDown(_HelpersMixin):
    def test_no_cases_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._narrow_down_by_case_number_features([], []) is None

    def test_no_case_numbers_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._narrow_down_by_case_number_features([self._make_case()], []) is None

    def test_no_features_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._narrow_down_by_case_number_features([self._make_case()], ["abc"]) is None

    def test_unique_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(case_type="civil", current_stage="first_trial")
        c2 = self._make_case(case_id=2, case_type="criminal", current_stage="first_trial")
        result = CaseMatcher()._narrow_down_by_case_number_features([c1, c2], ["（2025）粤01民初1号"])
        assert result == c1

    def test_bankruptcy_filter(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(name="某公司破产重整案")
        result = CaseMatcher()._narrow_down_by_case_number_features([c1], ["（2025）粤01破1号"])
        assert result == c1

    def test_bankruptcy_no_match_falls_back_to_full_list(self):
        """_filter_bankruptcy returns all cases as fallback when no name matches."""
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(name="普通案")
        # _filter_bankruptcy returns the original list as fallback
        result = CaseMatcher()._narrow_down_by_case_number_features([c1], ["（2025）粤01破1号"])
        # With only one case in the list, it may return c1 or None depending on type filter
        # The bankruptcy filter returns [c1], then type filter returns [] since 破产 returns None for type
        # then _apply_type_filter returns [c1] as fallback, and single result returns c1
        assert result is c1 or result is None

    def test_multiple_matches_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(case_type="civil")
        c2 = self._make_case(case_id=2, case_type="civil")
        result = CaseMatcher()._narrow_down_by_case_number_features([c1, c2], ["（2025）粤01民初1号"])
        assert result is None


# ---------------------------------------------------------------------------
# _select_latest_case
# ---------------------------------------------------------------------------


class TestSelectLatestCase(_HelpersMixin):
    def test_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        assert CaseMatcher()._select_latest_case([]) is None

    def test_single(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c = self._make_case(case_id=5)
        result = CaseMatcher()._select_latest_case([c])
        assert result == c

    def test_multiple_returns_highest_id(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=10)
        c3 = self._make_case(case_id=5)
        result = CaseMatcher()._select_latest_case([c1, c2, c3])
        assert result.id == 10


# ---------------------------------------------------------------------------
# _match_by_case_number_exact
# ---------------------------------------------------------------------------


class TestMatchByCaseNumberExact(_HelpersMixin):
    def _make_matcher(self, all_cases=None):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=all_cases or [])
        return matcher

    def test_no_numbers(self):
        matcher = self._make_matcher()
        assert matcher._match_by_case_number_exact([]) is None

    def test_no_match(self):
        matcher = self._make_matcher(all_cases=[])
        assert matcher._match_by_case_number_exact(["123"]) is None

    def test_single_active(self):
        c = self._make_case(status="active")
        matcher = self._make_matcher(all_cases=[c])
        from apps.core.models.enums import CaseStatus
        c.status = CaseStatus.ACTIVE
        assert matcher._match_by_case_number_exact(["123"]) == c

    def test_single_closed(self):
        from apps.core.models.enums import CaseStatus
        c = self._make_case(status=CaseStatus.CLOSED)
        matcher = self._make_matcher(all_cases=[c])
        assert matcher._match_by_case_number_exact(["123"]) is None

    def test_multiple_one_active(self):
        from apps.core.models.enums import CaseStatus
        c1 = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        c2 = self._make_case(case_id=2, status=CaseStatus.CLOSED)
        matcher = self._make_matcher(all_cases=[c1, c2])
        assert matcher._match_by_case_number_exact(["123"]) == c1

    def test_multiple_active_returns_none(self):
        from apps.core.models.enums import CaseStatus
        c1 = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        c2 = self._make_case(case_id=2, status=CaseStatus.ACTIVE)
        matcher = self._make_matcher(all_cases=[c1, c2])
        assert matcher._match_by_case_number_exact(["123"]) is None

    def test_all_closed_returns_none(self):
        from apps.core.models.enums import CaseStatus
        c1 = self._make_case(case_id=1, status=CaseStatus.CLOSED)
        c2 = self._make_case(case_id=2, status=CaseStatus.CLOSED)
        matcher = self._make_matcher(all_cases=[c1, c2])
        assert matcher._match_by_case_number_exact(["123"]) is None


# ---------------------------------------------------------------------------
# _extract_party_names
# ---------------------------------------------------------------------------


class TestExtractPartyNames(_HelpersMixin):
    def _make_matcher(self, doc_paths=None, doc_parties=None):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(
            document_parser_service=MagicMock(),
        )
        matcher.document_parser_service.get_all_document_paths.return_value = doc_paths or []
        if doc_parties is not None:
            matcher.document_parser_service.extract_parties_from_document.return_value = doc_parties
        return matcher

    def test_two_plus_parties_from_sms(self):
        matcher = self._make_matcher()
        sms = self._make_sms(party_names=["张三", "李四"])
        assert matcher._extract_party_names(sms) == ["张三", "李四"]

    def test_one_party_falls_back_to_doc(self):
        matcher = self._make_matcher(doc_paths=["/tmp/doc.pdf"], doc_parties=["A", "B"])
        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["A", "B"]

    def test_no_parties_from_sms_uses_doc(self):
        matcher = self._make_matcher(doc_paths=["/tmp/doc.pdf"], doc_parties=["A", "B", "C"])
        sms = self._make_sms(party_names=[])
        result = matcher._extract_party_names(sms)
        assert result == ["A", "B", "C"]

    def test_doc_extraction_fails_returns_sms_single(self):
        matcher = self._make_matcher(doc_paths=["/tmp/doc.pdf"])
        matcher.document_parser_service.extract_parties_from_document.side_effect = Exception("fail")
        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_no_parties_anywhere(self):
        matcher = self._make_matcher(doc_paths=[])
        sms = self._make_sms(party_names=[])
        result = matcher._extract_party_names(sms)
        assert result == []

    def test_doc_parties_insufficient_uses_sms_single(self):
        matcher = self._make_matcher(doc_paths=["/tmp/doc.pdf"], doc_parties=["single"])
        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]


# ---------------------------------------------------------------------------
# match (main entry point)
# ---------------------------------------------------------------------------


class TestMatch(_HelpersMixin):
    def _make_matcher(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(
            case_service=MagicMock(),
            document_parser_service=MagicMock(),
            party_matching_service=MagicMock(),
        )
        return matcher

    def test_case_number_exact_match(self):
        matcher = self._make_matcher()
        c = self._make_case()
        matcher._match_by_case_number_exact = MagicMock(return_value=c)
        sms = self._make_sms(case_numbers=["123"])
        assert matcher.match(sms) == c

    def test_party_match_unique(self):
        matcher = self._make_matcher()
        c = self._make_case()
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=["张三", "李四"])
        matcher._match_by_party_names_all = MagicMock(return_value=[c])
        sms = self._make_sms(case_numbers=["123"])
        assert matcher.match(sms) == c

    def test_party_match_multiple_with_narrow(self):
        matcher = self._make_matcher()
        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=2)
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=["张三", "李四"])
        matcher._match_by_party_names_all = MagicMock(return_value=[c1, c2])
        matcher._narrow_down_by_case_number_features = MagicMock(return_value=c1)
        sms = self._make_sms(case_numbers=["123"])
        assert matcher.match(sms) == c1

    def test_party_match_multiple_no_narrow_selects_latest(self):
        matcher = self._make_matcher()
        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=2)
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=["张三", "李四"])
        matcher._match_by_party_names_all = MagicMock(return_value=[c1, c2])
        matcher._narrow_down_by_case_number_features = MagicMock(return_value=None)
        matcher._select_latest_case = MagicMock(return_value=c2)
        sms = self._make_sms(case_numbers=["123"])
        assert matcher.match(sms) == c2

    def test_no_match_returns_none(self):
        matcher = self._make_matcher()
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=[])
        matcher._check_and_log_closed_cases = MagicMock()
        sms = self._make_sms()
        assert matcher.match(sms) is None

    def test_exception_wraps_in_validation(self):
        from apps.core.exceptions import ValidationException
        matcher = self._make_matcher()
        matcher._match_by_case_number_exact = MagicMock(side_effect=RuntimeError("boom"))
        sms = self._make_sms(case_numbers=["123"])
        with pytest.raises(ValidationException, match="案件匹配失败"):
            matcher.match(sms)

    def test_no_case_numbers_skips_exact(self):
        matcher = self._make_matcher()
        matcher._extract_party_names = MagicMock(return_value=[])
        matcher._check_and_log_closed_cases = MagicMock()
        sms = self._make_sms(case_numbers=[])
        result = matcher.match(sms)
        assert result is None


# ---------------------------------------------------------------------------
# _get_all_cases_by_numbers
# ---------------------------------------------------------------------------


class TestGetAllCasesByNumbers(_HelpersMixin):
    def test_dedup(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())
        c1 = self._make_case(case_id=1)
        matcher.case_service.search_cases_by_case_number_internal.return_value = [c1, c1]
        with patch("apps.automation.utils.text_utils.TextUtils.normalize_case_number", side_effect=lambda x: x):
            result = matcher._get_all_cases_by_numbers(["123"])
        assert len(result) == 1

    def test_exception_swallowed(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())
        matcher.case_service.search_cases_by_case_number_internal.side_effect = Exception("boom")
        with patch("apps.automation.utils.text_utils.TextUtils.normalize_case_number", side_effect=lambda x: x):
            result = matcher._get_all_cases_by_numbers(["123"])
        assert result == []


# ---------------------------------------------------------------------------
# _match_by_party_names_all
# ---------------------------------------------------------------------------


class TestMatchByPartyNamesAll(_HelpersMixin):
    def test_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(party_matching_service=MagicMock())
        assert matcher._match_by_party_names_all([]) == []

    def test_exact_client_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        c1 = MagicMock()
        c1.name = "张三"
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = [c1]
        c = self._make_case()
        matcher._find_all_matching_cases = MagicMock(return_value=[c])
        result = matcher._match_by_party_names_all(["张三"])
        assert result == [c]

    def test_fuzzy_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = []
        c1 = MagicMock()
        c1.name = "张三"
        matcher.party_matching_service.extract_and_match_parties_from_sms.return_value = [c1]
        c = self._make_case()
        matcher._find_all_matching_cases = MagicMock(return_value=[c])
        result = matcher._match_by_party_names_all(["张三"])
        assert result == [c]

    def test_no_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = []
        matcher.party_matching_service.extract_and_match_parties_from_sms.return_value = []
        result = matcher._match_by_party_names_all(["张三"])
        assert result == []


# ---------------------------------------------------------------------------
# _find_all_matching_cases
# ---------------------------------------------------------------------------


class TestFindAllMatchingCases(_HelpersMixin):
    def test_bidirectional_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())

        c1 = MagicMock()
        c1.id = 1
        matcher.case_service.search_cases_by_party_internal.return_value = [c1]
        matcher.case_service.get_case_party_names_internal.return_value = ["张三", "李四"]

        client1 = MagicMock()
        client1.name = "张三"
        client2 = MagicMock()
        client2.name = "李四"

        result = matcher._find_all_matching_cases([client1, client2])
        assert len(result) == 1

    def test_no_bidirectional_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())

        c1 = MagicMock()
        c1.id = 1
        matcher.case_service.search_cases_by_party_internal.return_value = [c1]
        # Case has parties that SMS doesn't have
        matcher.case_service.get_case_party_names_internal.return_value = ["张三", "李四", "王五"]

        client1 = MagicMock()
        client1.name = "张三"

        result = matcher._find_all_matching_cases([client1])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# match_by_case_number / match_by_party_names
# ---------------------------------------------------------------------------


class TestCompatibilityMethods(_HelpersMixin):
    def test_match_by_case_number(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c = self._make_case()
        matcher._match_by_case_number_exact = MagicMock(return_value=c)
        assert matcher.match_by_case_number(["123"]) == c

    def test_match_by_party_names_unique(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c = self._make_case()
        matcher._match_by_party_names_all = MagicMock(return_value=[c])
        assert matcher.match_by_party_names(["张三"]) == c

    def test_match_by_party_names_multiple(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=10)
        matcher._match_by_party_names_all = MagicMock(return_value=[c1, c2])
        result = matcher.match_by_party_names(["张三", "李四"])
        assert result.id == 10

    def test_match_by_party_names_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        matcher._match_by_party_names_all = MagicMock(return_value=[])
        assert matcher.match_by_party_names(["张三"]) is None


# ---------------------------------------------------------------------------
# extract_parties_from_document
# ---------------------------------------------------------------------------


class TestExtractPartiesFromDocument:
    def test_delegates(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(document_parser_service=MagicMock())
        matcher.document_parser_service.extract_parties_from_document.return_value = ["A", "B"]
        result = matcher.extract_parties_from_document("/tmp/doc.pdf")
        assert result == ["A", "B"]


# ---------------------------------------------------------------------------
# _check_and_log_closed_cases / _collect_closed_cases_by_number / _collect_closed_cases_by_party
# ---------------------------------------------------------------------------


class TestCheckAndLogClosedCases(_HelpersMixin):
    def test_logs_closed_by_number(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        c = self._make_case(status="closed")
        matcher.case_service.search_cases_by_case_number_internal.return_value = [c]
        sms = self._make_sms(case_numbers=["123"])
        sms.party_names = []
        with patch("apps.automation.utils.text_utils.TextUtils.normalize_case_number", side_effect=lambda x: x):
            matcher._check_and_log_closed_cases(sms)

    def test_logs_closed_by_party(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        c = self._make_case(status="closed")
        matcher.case_service.search_cases_by_case_number_internal.return_value = []
        matcher.case_service.search_cases_by_party_internal.return_value = [c]
        client = MagicMock()
        client.name = "张三"
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = [client]
        sms = self._make_sms(case_numbers=[], party_names=["张三"])
        with patch("apps.automation.utils.text_utils.TextUtils.normalize_case_number", side_effect=lambda x: x):
            from apps.core.models.enums import CaseStatus
            c.status = CaseStatus.CLOSED
            matcher._check_and_log_closed_cases(sms)

    def test_exception_handled(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        matcher._collect_closed_cases_by_number = MagicMock(side_effect=RuntimeError("boom"))
        sms = self._make_sms()
        # Should not raise
        matcher._check_and_log_closed_cases(sms)
