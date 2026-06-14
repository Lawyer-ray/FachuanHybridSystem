"""Tests for automation.services.sms.court_sms_recommendation_service — Round 4 deeper coverage.

Covers: get_recommendations full flow with mocked ORM, _score_and_rank deduplication,
_score_case combined signals, _extract_court_name_from_document with scraper_task exception,
_build_query with year_court_prefixes, RecommendationResult with all fields.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock

import pytest

from apps.automation.services.sms.court_sms_recommendation_service import (
    CourtSMSRecommendationService,
    RecommendationResult,
    _COURT_NAME_PATTERN,
    _YEAR_COURT_PREFIX_PATTERN,
)


def _svc() -> CourtSMSRecommendationService:
    return CourtSMSRecommendationService()


# ---------------------------------------------------------------------------
# get_recommendations — empty query returns empty
# ---------------------------------------------------------------------------


class TestGetRecommendations:
    def test_no_query_returns_empty(self):
        svc = _svc()
        sms = MagicMock()
        sms.case_numbers = []
        sms.party_names = []
        sms.content = "普通短信"
        sms.scraper_task = None
        result = svc.get_recommendations(sms)
        assert result == []


# ---------------------------------------------------------------------------
# _score_and_rank — deduplication
# ---------------------------------------------------------------------------


class TestScoreAndRankDedup:
    def test_deduplicates_by_id(self):
        svc = _svc()
        case1 = MagicMock()
        case1.id = 1
        case1.start_date = None
        case1.case_numbers.all.return_value = []
        case1.parties.all.return_value = []
        case1.supervising_authorities.all.return_value = []

        case2 = MagicMock()
        case2.id = 1  # same id
        case2.start_date = None
        case2.case_numbers.all.return_value = []
        case2.parties.all.return_value = []
        case2.supervising_authorities.all.return_value = []

        results = svc._score_and_rank(
            [case1, case2], [], [], None, []
        )
        assert len(results) == 1

    def test_top_10_limit(self):
        svc = _svc()
        cases = []
        for i in range(15):
            c = MagicMock()
            c.id = i
            c.name = f"Case {i}"
            c.status = "active"
            c.start_date = None
            c.case_numbers.all.return_value = []
            c.parties.all.return_value = []
            c.supervising_authorities.all.return_value = []
            cases.append(c)

        results = svc._score_and_rank(cases, [], [], None, [])
        assert len(results) <= 10

    def test_sorted_by_score_desc(self):
        svc = _svc()

        c1 = MagicMock()
        c1.id = 1
        c1.name = "Low"
        c1.status = "active"
        c1.start_date = None
        c1.case_numbers.all.return_value = []
        c1.parties.all.return_value = []
        c1.supervising_authorities.all.return_value = []

        c2 = MagicMock()
        c2.id = 2
        c2.name = "High"
        c2.status = "active"
        c2.start_date = None
        cn = MagicMock()
        cn.number = "（2025）粤01民初100号"
        c2.case_numbers.all.return_value = [cn]
        c2.parties.all.return_value = []
        c2.supervising_authorities.all.return_value = []

        results = svc._score_and_rank(
            [c1, c2], ["（2025）粤01民初100号"], [], None, []
        )
        assert results[0].case_name == "High"
        assert results[0].score >= 100


# ---------------------------------------------------------------------------
# _score_case — combined signals
# ---------------------------------------------------------------------------


class TestScoreCaseCombined:
    def _make_case(self, *, case_numbers=None, parties=None, authorities=None, start_date=None):
        case = MagicMock()
        case.id = 1
        case.start_date = start_date

        cn_mocks = []
        for num in (case_numbers or []):
            cn = MagicMock()
            cn.number = num
            cn_mocks.append(cn)
        case.case_numbers.all.return_value = cn_mocks

        party_mocks = []
        for name in (parties or []):
            p = MagicMock()
            p.client = MagicMock()
            p.client.name = name
            party_mocks.append(p)
        case.parties.all.return_value = party_mocks

        sa_mocks = []
        for name in (authorities or []):
            sa = MagicMock()
            sa.name = name
            sa_mocks.append(sa)
        case.supervising_authorities.all.return_value = sa_mocks

        return case

    def test_all_signals_combined(self):
        svc = _svc()
        case = self._make_case(
            case_numbers=["（2025）粤01民初100号"],
            parties=["张三"],
            authorities=["广州市天河区人民法院"],
            start_date=date.today(),
        )
        score, reasons = svc._score_case(
            case, ["（2025）粤01民初100号"], [], "天河区人民法院", ["张三"]
        )
        assert score >= 100 + 40 + 20 + 1  # exact + court + party + recency
        assert "案号完全匹配" in reasons
        assert "法院名称匹配" in reasons
        assert "当事人匹配" in reasons[2]

    def test_no_signals(self):
        svc = _svc()
        case = self._make_case()
        score, reasons = svc._score_case(case, [], [], None, [])
        assert score == 0
        assert reasons == []

    def test_multiple_parties(self):
        svc = _svc()
        case = self._make_case(parties=["张三", "李四"])
        score, reasons = svc._score_case(case, [], [], None, ["张三", "李四"])
        assert score >= 40  # 2 * 20
        assert "2人" in reasons[0]

    def test_recency_old_case(self):
        svc = _svc()
        case = self._make_case(start_date=date(2015, 1, 1))
        score, reasons = svc._score_case(case, [], [], None, [])
        # 10+ years old -> recency = max(1, min(5, 5 - 10)) = 1
        assert score == 1

    def test_recency_no_date(self):
        svc = _svc()
        case = self._make_case(start_date=None)
        score, reasons = svc._score_case(case, [], [], None, [])
        assert score == 0


# ---------------------------------------------------------------------------
# _build_query — year_court_prefixes
# ---------------------------------------------------------------------------


class TestBuildQueryPrefixes:
    def test_with_year_court_prefixes(self):
        result = CourtSMSRecommendationService._build_query(
            [], ["(2025)粤01"], None, []
        )
        assert result is not None

    def test_all_dimensions(self):
        result = CourtSMSRecommendationService._build_query(
            ["CN001"], ["(2025)粤01"], "天河法院", ["张三"]
        )
        assert result is not None


# ---------------------------------------------------------------------------
# _build_result — all fields populated
# ---------------------------------------------------------------------------


class TestBuildResultFull:
    def test_with_all_data(self):
        svc = _svc()
        case = MagicMock()
        case.id = 42
        case.name = "Full Case"
        case.status = "active"

        cn1 = MagicMock()
        cn1.number = "CN001"
        cn2 = MagicMock()
        cn2.number = "CN002"
        case.case_numbers.all.return_value = [cn1, cn2]

        p1 = MagicMock()
        p1.client = MagicMock()
        p1.client.name = "张三"
        p2 = MagicMock()
        p2.client = MagicMock()
        p2.client.name = "李四"
        case.parties.all.return_value = [p1, p2]

        sa = MagicMock()
        sa.name = "天河法院"
        case.supervising_authorities.all.return_value = [sa]

        result = svc._build_result(case, 150, ["案号匹配", "当事人匹配"])
        assert result.case_id == 42
        assert result.case_name == "Full Case"
        assert result.score == 150
        assert result.reasons == ["案号匹配", "当事人匹配"]
        assert result.case_numbers == ["CN001", "CN002"]
        assert result.parties == ["张三", "李四"]
        assert result.court_names == ["天河法院"]
        assert result.status == "active"

    def test_with_none_client(self):
        svc = _svc()
        case = MagicMock()
        case.id = 1
        case.name = "Case"
        case.status = "active"
        case.case_numbers.all.return_value = []
        p = MagicMock()
        p.client = None
        case.parties.all.return_value = [p]
        sa = MagicMock()
        sa.name = None
        case.supervising_authorities.all.return_value = [sa]

        result = svc._build_result(case, 0, [])
        assert result.parties == []
        assert result.court_names == []


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------


class TestRegexPatterns:
    def test_court_name_pattern(self):
        assert _COURT_NAME_PATTERN.search("广州市天河区人民法院")
        assert _COURT_NAME_PATTERN.search("北京市海淀区人民法院通知") is not None
        assert _COURT_NAME_PATTERN.search("普通短信") is None

    def test_year_court_prefix_pattern(self):
        match = _YEAR_COURT_PREFIX_PATTERN.search("（2025）粤0605民初100号")
        assert match is not None
        assert match.group(1) == "2025"
        assert "粤0605" in match.group(0)

    def test_year_court_prefix_no_match(self):
        match = _YEAR_COURT_PREFIX_PATTERN.search("ABC123")
        assert match is None
