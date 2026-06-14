"""oa_filing/services/oa_scripts/jtn/case_import/service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
from apps.oa_filing.services.oa_scripts.jtn.models import OACaseData, OAListCaseCandidate


@pytest.fixture
def script() -> JtnCaseImportScript:
    return JtnCaseImportScript(
        account="user@test.com",
        password="pass123",  # pragma: allowlist secret
        headless=True,
    )


# ── __init__ ──────────────────────────────────────────────────────────


class TestInit:
    def test_defaults(self, script: JtnCaseImportScript) -> None:
        assert script._account == "user@test.com"
        assert script._password == "pass123"  # pragma: allowlist secret
        assert script._headless is True
        assert script._page is None
        assert script._context is None

    def test_progress_callback(self) -> None:
        cb = MagicMock()
        s = JtnCaseImportScript("a", "b", progress_callback=cb)  # pragma: allowlist secret
        assert s._progress_callback is cb


# ── search_case (single) ──────────────────────────────────────────────


class TestSearchCase:
    def test_empty_case_no_returns_none(self, script: JtnCaseImportScript) -> None:
        assert script.search_case("") is None
        assert script.search_case("   ") is None

    def test_delegates_to_search_cases(self, script: JtnCaseImportScript) -> None:
        case_data = OACaseData(case_no="2024GZM0501", keyid="k1")
        with patch.object(script, "search_cases", return_value=iter([("2024GZM0501", case_data)])):
            result = script.search_case("2024GZM0501")
            assert result is case_data

    def test_not_found(self, script: JtnCaseImportScript) -> None:
        with patch.object(script, "search_cases", return_value=iter([])):
            assert script.search_case("2024GZM0501") is None


# ── search_cases_by_name ──────────────────────────────────────────────


class TestSearchCasesByName:
    def test_empty_keyword(self, script: JtnCaseImportScript) -> None:
        assert script.search_cases_by_name("") == []
        assert script.search_cases_by_name(None) == []  # type: ignore[arg-type]

    def test_http_path(self, script: JtnCaseImportScript) -> None:
        candidate = OAListCaseCandidate(
            case_no="c1", case_name="name", keyid="k", detail_url="http://x"
        )
        with patch.object(script, "_search_cases_by_name_via_http", return_value=[candidate]):
            result = script.search_cases_by_name("test")
            assert len(result) == 1

    def test_playwright_fallback(self, script: JtnCaseImportScript) -> None:
        script._force_playwright_name_search = True
        candidate = OAListCaseCandidate(
            case_no="c1", case_name="n", keyid="k", detail_url="http://x"
        )
        with patch.object(script, "_search_cases_by_name_via_playwright", return_value=[candidate]):
            result = script.search_cases_by_name("test")
            assert len(result) == 1

    def test_http_error_fallback_pw(self, script: JtnCaseImportScript) -> None:
        candidate = OAListCaseCandidate(
            case_no="c1", case_name="n", keyid="k", detail_url="http://x"
        )
        with patch.object(script, "_search_cases_by_name_via_http", side_effect=RuntimeError("http fail")), \
             patch.object(script, "_search_cases_by_name_via_playwright", return_value=[candidate]):
            result = script.search_cases_by_name("test")
            assert len(result) == 1

    def test_both_fail(self, script: JtnCaseImportScript) -> None:
        with patch.object(script, "_search_cases_by_name_via_http", side_effect=RuntimeError("fail")), \
             patch.object(script, "_search_cases_by_name_via_playwright", return_value=[]):
            result = script.search_cases_by_name("test")
            assert result == []


# ── ensure_name_search_ready ──────────────────────────────────────────


class TestEnsureNameSearchReady:
    def test_sets_flag(self, script: JtnCaseImportScript) -> None:
        with patch.object(script, "_ensure_name_search_playwright_session"):
            script.ensure_name_search_ready()
            assert script._force_playwright_name_search is True


# ── _emit_progress ────────────────────────────────────────────────────


class TestEmitProgress:
    def test_with_callback(self, script: JtnCaseImportScript) -> None:
        cb = MagicMock()
        script._progress_callback = cb
        script._emit_progress("test_event", case_no="c1", message="hi")
        cb.assert_called_once_with({"event": "test_event", "case_no": "c1", "message": "hi"})

    def test_no_callback(self, script: JtnCaseImportScript) -> None:
        script._emit_progress("event")  # Should not raise

    def test_callback_exception_swallowed(self, script: JtnCaseImportScript) -> None:
        cb = MagicMock(side_effect=Exception("oops"))
        script._progress_callback = cb
        script._emit_progress("event")  # Should not raise


# ── search_cases (batch) ─────────────────────────────────────────────


class TestSearchCases:
    def test_empty_list(self, script: JtnCaseImportScript) -> None:
        results = list(script.search_cases([]))
        assert results == []

    def test_whitespace_only_filtered(self, script: JtnCaseImportScript) -> None:
        results = list(script.search_cases(["  ", ""]))
        assert results == []

    def test_http_success(self, script: JtnCaseImportScript) -> None:
        case_data = OACaseData(case_no="c1", keyid="k1")
        with patch.object(script, "_search_cases_via_http", return_value=[(0, "c1", case_data)]):
            results = list(script.search_cases(["c1"]))
            assert len(results) == 1
            assert results[0][1] is case_data

    def test_http_failure_fallback(self, script: JtnCaseImportScript) -> None:
        case_data = OACaseData(case_no="c1", keyid="k1")
        with patch.object(script, "_search_cases_via_http", side_effect=RuntimeError("fail")), \
             patch.object(script, "_search_cases_via_playwright", return_value=[("c1", case_data)]):
            results = list(script.search_cases(["c1"]))
            assert len(results) == 1

    def test_http_none_result_fallback(self, script: JtnCaseImportScript) -> None:
        case_data = OACaseData(case_no="c1", keyid="k1")
        with patch.object(script, "_search_cases_via_http", return_value=[(0, "c1", None)]), \
             patch.object(script, "_search_cases_via_playwright", return_value=[("c1", case_data)]):
            results = list(script.search_cases(["c1"]))
            assert results[0][1] is case_data

    def test_playwright_fallback_exception(self, script: JtnCaseImportScript) -> None:
        with patch.object(script, "_search_cases_via_http", side_effect=RuntimeError("fail")), \
             patch.object(script, "_search_cases_via_playwright", side_effect=RuntimeError("pw fail")):
            results = list(script.search_cases(["c1"]))
            assert results[0][1] is None
