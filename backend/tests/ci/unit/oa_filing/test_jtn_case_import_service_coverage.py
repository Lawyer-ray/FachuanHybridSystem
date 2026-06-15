"""Tests for oa_filing/services/oa_scripts/jtn/case_import/service.py — uncovered branches.

Covers: JtnCaseImportScript init, search_case, search_cases_by_name,
search_cases, close, _emit_progress, ensure_name_search_ready.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestJtnCaseImportScriptInit:
    def test_init(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="test", password="pass")
        assert svc._account == "test"
        assert svc._password == "pass"
        assert svc._headless is True
        assert svc._progress_callback is None
        assert svc._page is None
        assert svc._context is None
        assert svc._http_cookies_cache is None
        assert svc._force_playwright_name_search is False

    def test_init_with_params(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        cb = MagicMock()
        svc = JtnCaseImportScript(
            account="a", password="p", headless=False, progress_callback=cb
        )
        assert svc._headless is False
        assert svc._progress_callback is cb


class TestSearchCase:
    def test_empty_case_no(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        assert svc.search_case("") is None
        assert svc.search_case("  ") is None

    def test_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        mock_case_data = MagicMock()
        with patch.object(svc, 'search_cases', return_value=iter([("2024GZM0501", mock_case_data)])):
            result = svc.search_case("2024GZM0501")
            assert result is mock_case_data

    def test_not_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        with patch.object(svc, 'search_cases', return_value=iter([])):
            result = svc.search_case("2024GZM0501")
            assert result is None


class TestSearchCasesByName:
    def test_empty_keyword(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        assert svc.search_cases_by_name("") == []
        assert svc.search_cases_by_name(None) == []

    def test_force_playwright(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        svc._force_playwright_name_search = True
        with patch.object(svc, '_search_cases_by_name_via_playwright', return_value=[MagicMock()]) as mock_pw:
            result = svc.search_cases_by_name("test", limit=3)
            assert len(result) == 1
            mock_pw.assert_called_once_with(keyword="test", limit=3)

    def test_http_success(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        mock_candidate = MagicMock()
        with patch.object(svc, '_search_cases_by_name_via_http', return_value=[mock_candidate]):
            result = svc.search_cases_by_name("合同")
            assert len(result) == 1

    def test_http_error_sso_raises(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        with patch.object(svc, '_search_cases_by_name_via_http', side_effect=RuntimeError("sso")):
            with patch.object(svc, '_is_sso_blocking_error', return_value=True):
                with pytest.raises(RuntimeError):
                    svc.search_cases_by_name("合同")


class TestSearchCases:
    def test_empty_case_nos(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        results = list(svc.search_cases([]))
        assert results == []

    def test_http_success(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        mock_data = MagicMock()
        with patch.object(svc, '_search_cases_via_http', return_value=[(0, "2024GZM0501", mock_data)]):
            with patch.object(svc, '_emit_progress'):
                results = list(svc.search_cases(["2024GZM0501"]))
                assert len(results) == 1
                assert results[0][1] is mock_data

    def test_http_exception_fallback_to_playwright(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        mock_data = MagicMock()
        with patch.object(svc, '_search_cases_via_http', side_effect=RuntimeError("http fail")):
            with patch.object(svc, '_search_cases_via_playwright', return_value=[("2024GZM0501", mock_data)]):
                with patch.object(svc, '_emit_progress'):
                    results = list(svc.search_cases(["2024GZM0501"], playwright_fallback=True))
                    assert len(results) == 1
                    assert results[0][1] is mock_data

    def test_no_fallback(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        with patch.object(svc, '_search_cases_via_http', side_effect=RuntimeError("fail")):
            with patch.object(svc, '_emit_progress'):
                results = list(svc.search_cases(["2024GZM0501"], playwright_fallback=False))
                assert len(results) == 1
                assert results[0][1] is None


class TestEmitProgress:
    def test_no_callback(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        svc._emit_progress("event")  # should not raise

    def test_with_callback(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        cb = MagicMock()
        svc = JtnCaseImportScript(account="a", password="p", progress_callback=cb)
        svc._emit_progress("event", case_no="123")
        cb.assert_called_once_with({"event": "event", "case_no": "123"})

    def test_callback_exception(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        cb = MagicMock(side_effect=RuntimeError("fail"))
        svc = JtnCaseImportScript(account="a", password="p", progress_callback=cb)
        svc._emit_progress("event")  # should not raise


class TestEnsureNameSearchReady:
    def test_sets_flag(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.service import JtnCaseImportScript
        svc = JtnCaseImportScript(account="a", password="p")
        with patch.object(svc, '_ensure_name_search_playwright_session'):
            svc.ensure_name_search_ready()
            assert svc._force_playwright_name_search is True
