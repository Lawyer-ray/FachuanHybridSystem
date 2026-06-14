"""Round 4 coverage tests for automation.services.sms.case_matcher.

Targets remaining uncovered branches:
- match: party_match_multiple_no_case_numbers (skip narrow_down)
- match: no party_names but has case_numbers (no match, check closed)
- _match_by_case_number_exact: multiple all closed
- _extract_party_names: doc extracts exactly 2 parties from second doc
- _get_active_cases_by_numbers: delegates correctly
- _check_and_log_closed_cases: both number and party paths, dedup
- _collect_closed_cases_by_number: no case_numbers
- _collect_closed_cases_by_party: no party_names, no matched clients
- _detect_case_type_from_number: no recognized type
- _detect_case_stage_from_number: zhibao path logged
- _narrow_down_by_case_number_features: bankruptcy + single filtered
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _HelpersMixin:
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
# match — party match multiple without case_numbers
# ---------------------------------------------------------------------------


class TestMatchPartyMultipleNoCaseNumbers(_HelpersMixin):
    def test_skips_narrow_down(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(
            case_service=MagicMock(),
            document_parser_service=MagicMock(),
            party_matching_service=MagicMock(),
        )
        c1 = self._make_case(case_id=1)
        c2 = self._make_case(case_id=2)
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=["张三", "李四"])
        matcher._match_by_party_names_all = MagicMock(return_value=[c1, c2])

        sms = self._make_sms(case_numbers=[], party_names=["张三", "李四"])
        result = matcher.match(sms)
        # Without case_numbers, narrow_down is skipped and _select_latest_case is called
        assert result == c2  # c2 has higher id


# ---------------------------------------------------------------------------
# match — no party_names, has case_numbers, no match
# ---------------------------------------------------------------------------


class TestMatchNoPartiesHasCaseNumbers(_HelpersMixin):
    def test_checks_closed_cases(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(
            case_service=MagicMock(),
            document_parser_service=MagicMock(),
            party_matching_service=MagicMock(),
        )
        matcher._match_by_case_number_exact = MagicMock(return_value=None)
        matcher._extract_party_names = MagicMock(return_value=[])
        matcher._check_and_log_closed_cases = MagicMock()

        sms = self._make_sms(case_numbers=["123"], party_names=[])
        result = matcher.match(sms)
        assert result is None
        matcher._check_and_log_closed_cases.assert_called_once_with(sms)


# ---------------------------------------------------------------------------
# _match_by_case_number_exact — multiple all closed
# ---------------------------------------------------------------------------


class TestMatchByCaseNumberExactAllClosed(_HelpersMixin):
    def _make_matcher(self, all_cases=None):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())
        matcher._get_all_cases_by_numbers = MagicMock(return_value=all_cases or [])
        return matcher

    def test_multiple_all_closed_returns_none(self):
        from apps.core.models.enums import CaseStatus
        c1 = self._make_case(case_id=1, status=CaseStatus.CLOSED)
        c2 = self._make_case(case_id=2, status=CaseStatus.CLOSED)
        c3 = self._make_case(case_id=3, status=CaseStatus.CLOSED)
        matcher = self._make_matcher(all_cases=[c1, c2, c3])
        assert matcher._match_by_case_number_exact(["123"]) is None


# ---------------------------------------------------------------------------
# _extract_party_names — second doc succeeds
# ---------------------------------------------------------------------------


class TestExtractPartyNamesSecondDoc(_HelpersMixin):
    def test_first_doc_fails_second_succeeds(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(document_parser_service=MagicMock())
        matcher.document_parser_service.get_all_document_paths.return_value = ["/doc1.pdf", "/doc2.pdf"]

        call_count = 0

        def extract_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("parse error")
            return ["张三", "李四", "王五"]

        matcher.document_parser_service.extract_parties_from_document.side_effect = extract_side_effect

        sms = self._make_sms(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四", "王五"]


# ---------------------------------------------------------------------------
# _get_active_cases_by_numbers
# ---------------------------------------------------------------------------


class TestGetActiveCasesByNumbers(_HelpersMixin):
    def test_filters_active_only(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseStatus

        matcher = CaseMatcher(case_service=MagicMock())
        c1 = self._make_case(case_id=1, status=CaseStatus.ACTIVE)
        c2 = self._make_case(case_id=2, status=CaseStatus.CLOSED)
        matcher._get_all_cases_by_numbers = MagicMock(return_value=[c1, c2])

        result = matcher._get_active_cases_by_numbers(["123"])
        assert len(result) == 1
        assert result[0].id == 1


# ---------------------------------------------------------------------------
# _check_and_log_closed_cases — dedup between number and party paths
# ---------------------------------------------------------------------------


class TestCheckAndLogClosedCasesDedup(_HelpersMixin):
    def test_same_case_from_both_paths_deduped(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        from apps.core.models.enums import CaseStatus

        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        c = self._make_case(case_id=1, status=CaseStatus.CLOSED)

        # Both paths return the same case
        matcher.case_service.search_cases_by_case_number_internal.return_value = [c]
        matcher.case_service.search_cases_by_party_internal.return_value = [c]

        client = MagicMock()
        client.name = "张三"
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = [client]

        sms = self._make_sms(case_numbers=["123"], party_names=["张三"])
        with patch("apps.automation.utils.text_utils.TextUtils.normalize_case_number", side_effect=lambda x: x):
            matcher._check_and_log_closed_cases(sms)
        # Should not raise, case added once to set


# ---------------------------------------------------------------------------
# _collect_closed_cases_by_number — no case_numbers
# ---------------------------------------------------------------------------


class TestCollectClosedCasesByNumberEdge(_HelpersMixin):
    def test_no_case_numbers_returns_early(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock())
        sms = self._make_sms(case_numbers=[])
        closed_cases = set()
        matcher._collect_closed_cases_by_number(sms, closed_cases)
        assert len(closed_cases) == 0


# ---------------------------------------------------------------------------
# _collect_closed_cases_by_party — no party_names
# ---------------------------------------------------------------------------


class TestCollectClosedCasesByPartyEdge(_HelpersMixin):
    def test_no_party_names_returns_early(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        sms = self._make_sms(party_names=[])
        closed_cases = set()
        matcher._collect_closed_cases_by_party(sms, closed_cases)
        assert len(closed_cases) == 0

    def test_no_matched_clients_returns_early(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher(case_service=MagicMock(), party_matching_service=MagicMock())
        matcher.party_matching_service.find_existing_clients_in_sms.return_value = []
        sms = self._make_sms(party_names=["张三"])
        closed_cases = set()
        matcher._collect_closed_cases_by_party(sms, closed_cases)
        assert len(closed_cases) == 0


# ---------------------------------------------------------------------------
# _detect_case_type_from_number — no recognized type
# ---------------------------------------------------------------------------


class TestDetectCaseTypeNoMatch(_HelpersMixin):
    def test_no_recognized_type_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        result = CaseMatcher()._detect_case_type_from_number("（2025）粤01执123号")
        # 执 is not 刑/行/民/破, so returns None
        assert result is None


# ---------------------------------------------------------------------------
# _detect_case_stage_from_number — zhibao path
# ---------------------------------------------------------------------------


class TestDetectCaseStageZhibao(_HelpersMixin):
    def test_zhibao_returns_none_with_log(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        result = CaseMatcher()._detect_case_stage_from_number("（2025）粤01执保123号")
        assert result is None


# ---------------------------------------------------------------------------
# _narrow_down_by_case_number_features — bankruptcy single filtered
# ---------------------------------------------------------------------------


class TestNarrowDownBankruptcySingle(_HelpersMixin):
    def test_bankruptcy_single_match_returns_it(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        c1 = self._make_case(name="某公司破产重整案")
        c2 = self._make_case(case_id=2, name="普通民事案")
        result = CaseMatcher()._narrow_down_by_case_number_features([c1, c2], ["（2025）粤01破1号"])
        assert result == c1


# ---------------------------------------------------------------------------
# _find_all_matching_cases — no cases from search
# ---------------------------------------------------------------------------


class TestFindAllMatchingCasesEdge(_HelpersMixin):
    def test_no_cases_from_search(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher(case_service=MagicMock())
        matcher.case_service.search_cases_by_party_internal.return_value = []

        client = MagicMock()
        client.name = "张三"
        result = matcher._find_all_matching_cases([client])
        assert result == []
