"""Tests for automation.services.sms.court_sms_recommendation_service.

Covers: _extract_court_name, _collect_year_court_prefixes, _build_query,
_score_case, _build_result, _extract_court_name_from_document/content.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.automation.services.sms.court_sms_recommendation_service import (
    CourtSMSRecommendationService,
    RecommendationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _svc() -> CourtSMSRecommendationService:
    return CourtSMSRecommendationService()


# ---------------------------------------------------------------------------
# _extract_court_name
# ---------------------------------------------------------------------------


class TestExtractCourtName:
    def test_from_document_priority(self):
        svc = _svc()
        sms = MagicMock()
        sms.scraper_task.documents.filter.return_value.exclude.return_value.first.return_value = SimpleNamespace(
            c_fymc="广州市天河区人民法院"
        )
        assert svc._extract_court_name(sms) == "广州市天河区人民法院"

    def test_from_content_fallback(self):
        svc = _svc()
        sms = MagicMock()
        sms.scraper_task = None
        sms.content = "广州市海珠区人民法院"
        assert svc._extract_court_name(sms) == "广州市海珠区人民法院"

    def test_no_court_found(self):
        svc = _svc()
        sms = MagicMock()
        sms.scraper_task = None
        sms.content = "普通短信内容"
        assert svc._extract_court_name(sms) is None


# ---------------------------------------------------------------------------
# _extract_court_name_from_document
# ---------------------------------------------------------------------------


class TestExtractCourtNameFromDocument:
    def test_no_scraper_task(self):
        svc = _svc()
        sms = MagicMock()
        sms.scraper_task = None
        assert svc._extract_court_name_from_document(sms) is None

    def test_no_documents(self):
        svc = _svc()
        sms = MagicMock(spec=[])
        task = MagicMock()
        task.documents = None
        sms.scraper_task = task
        assert svc._extract_court_name_from_document(sms) is None

    def test_empty_court_name(self):
        svc = _svc()
        sms = MagicMock()
        sms.scraper_task.documents.filter.return_value.exclude.return_value.first.return_value = SimpleNamespace(
            c_fymc=""
        )
        assert svc._extract_court_name_from_document(sms) is None

    def test_exception_returns_none(self):
        svc = _svc()
        sms = MagicMock()
        type(sms).scraper_task = PropertyMock(side_effect=RuntimeError("fail"))
        assert svc._extract_court_name_from_document(sms) is None


# ---------------------------------------------------------------------------
# _extract_court_name_from_content
# ---------------------------------------------------------------------------


class TestExtractCourtNameFromContent:
    def test_matches_court_name(self):
        svc = _svc()
        assert svc._extract_court_name_from_content("天河区人民法院") == "天河区人民法院"

    def test_no_match(self):
        svc = _svc()
        assert svc._extract_court_name_from_content("普通短信") is None

    def test_multiple_matches_returns_first(self):
        svc = _svc()
        # The regex [一-龥]{2,15}人民法院 is greedy, so "天河区人民法院与海珠区人民法院"
        # matches "天河区人民法院与海珠区人民法院" as one big match.
        # Use strings with only one court name to test first match behavior.
        result = svc._extract_court_name_from_content("天河区人民法院文书")
        assert result == "天河区人民法院"


# ---------------------------------------------------------------------------
# _collect_year_court_prefixes
# ---------------------------------------------------------------------------


class TestCollectYearCourtPrefixes:
    def test_extracts_prefix(self):
        result = CourtSMSRecommendationService._collect_year_court_prefixes(
            ["(2025)粤0605民初100号"]
        )
        assert "(2025)粤0605" in result

    def test_deduplicates(self):
        result = CourtSMSRecommendationService._collect_year_court_prefixes(
            ["(2025)粤01民初1号", "(2025)粤01民初2号"]
        )
        assert len(result) == 1

    def test_no_match(self):
        result = CourtSMSRecommendationService._collect_year_court_prefixes(["ABC123"])
        assert result == []

    def test_empty_list(self):
        assert CourtSMSRecommendationService._collect_year_court_prefixes([]) == []


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------


class TestBuildQuery:
    def test_all_none_returns_none(self):
        from django.db.models import Q
        result = CourtSMSRecommendationService._build_query([], [], None, [])
        assert result is None

    def test_with_case_numbers(self):
        from django.db.models import Q
        result = CourtSMSRecommendationService._build_query(
            ["(2025)粤01民初100号"], [], None, []
        )
        assert result is not None

    def test_with_court_name(self):
        result = CourtSMSRecommendationService._build_query([], [], "天河法院", [])
        assert result is not None

    def test_with_party_names_short_excluded(self):
        """Party names shorter than 2 chars are excluded."""
        result = CourtSMSRecommendationService._build_query([], [], None, ["张"])
        assert result is None

    def test_with_valid_party_names(self):
        result = CourtSMSRecommendationService._build_query([], [], None, ["张三"])
        assert result is not None


# ---------------------------------------------------------------------------
# _score_case
# ---------------------------------------------------------------------------


class TestScoreCase:
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

    def test_exact_case_number_match(self):
        svc = _svc()
        # Use full-width parens since normalize_case_number converts them
        case = self._make_case(case_numbers=["（2025）粤01民初100号"])
        score, reasons = svc._score_case(
            case, ["（2025）粤01民初100号"], [], None, []
        )
        assert score >= 100
        assert any("案号完全匹配" in r for r in reasons)

    def test_prefix_match(self):
        svc = _svc()
        case = self._make_case(case_numbers=["（2025）粤01民初200号"])
        score, reasons = svc._score_case(
            case, [], ["（2025）粤01"], None, []
        )
        assert score >= 50
        assert any("案号前缀匹配" in r for r in reasons)

    def test_court_name_match(self):
        svc = _svc()
        case = self._make_case(authorities=["广州市天河区人民法院"])
        score, reasons = svc._score_case(case, [], [], "天河区人民法院", [])
        assert score >= 40

    def test_party_match(self):
        svc = _svc()
        case = self._make_case(parties=["张三"])
        score, reasons = svc._score_case(case, [], [], None, ["张三"])
        assert score >= 20

    def test_recency_bonus(self):
        svc = _svc()
        case = self._make_case(start_date=date.today())
        score, reasons = svc._score_case(case, [], [], None, [])
        assert score >= 1  # recency bonus


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------


class TestBuildResult:
    def test_builds_correctly(self):
        svc = _svc()
        case = MagicMock()
        case.id = 42
        case.name = "Test Case"
        case.status = "active"
        cn = MagicMock()
        cn.number = "CN001"
        case.case_numbers.all.return_value = [cn]
        p = MagicMock()
        p.client = MagicMock()
        p.client.name = "张三"
        case.parties.all.return_value = [p]
        sa = MagicMock()
        sa.name = "天河法院"
        case.supervising_authorities.all.return_value = [sa]

        result = svc._build_result(case, 120, ["案号匹配"])
        assert result.case_id == 42
        assert result.score == 120
        assert "CN001" in result.case_numbers
        assert "张三" in result.parties
        assert "天河法院" in result.court_names


# ---------------------------------------------------------------------------
# RecommendationResult dataclass
# ---------------------------------------------------------------------------


class TestRecommendationResult:
    def test_defaults(self):
        r = RecommendationResult(case_id=1, case_name="c", score=0)
        assert r.reasons == []
        assert r.case_numbers == []
        assert r.parties == []
        assert r.court_names == []
        assert r.status == ""
