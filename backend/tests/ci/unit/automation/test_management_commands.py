"""Tests for automation management commands."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError


class TestClearTokenCacheCommand:
    def test_plan_mode_site(self) -> None:
        from apps.automation.management.commands.clear_token_cache import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd._print_plan(site="test_site", accounts=[], do_blacklist=False, do_all=False)
        cmd.stdout.write.assert_called()

    def test_plan_mode_all(self) -> None:
        from apps.automation.management.commands.clear_token_cache import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd._print_plan(site=None, accounts=[], do_blacklist=False, do_all=True)
        cmd.stdout.write.assert_called()

    def test_all_with_site_raises(self) -> None:
        from apps.automation.management.commands.clear_token_cache import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        with pytest.raises(CommandError):
            cmd.handle(all=True, site="test", account=[], blacklist=False, execute=False)

    def test_no_site_no_all_raises(self) -> None:
        from apps.automation.management.commands.clear_token_cache import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        with pytest.raises(CommandError):
            cmd.handle(all=False, site=None, account=[], blacklist=False, execute=False)


class TestDownloadOcrModelsCommand:
    def test_handle_success(self) -> None:
        from apps.automation.management.commands.download_ocr_models import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.ERROR = lambda x: x

        with patch("apps.automation.services.ocr.get_ocr_engine") as mock_ocr:
            mock_ocr.return_value = MagicMock()
            cmd.handle()
            mock_ocr.assert_called_once_with(use_v5=True)

    def test_handle_failure(self) -> None:
        from apps.automation.management.commands.download_ocr_models import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.ERROR = lambda x: x

        with patch("apps.automation.services.ocr.get_ocr_engine") as mock_ocr:
            mock_ocr.side_effect = RuntimeError("download failed")
            cmd.handle()
            cmd.stdout.write.assert_called()


class TestBenchHttpCommand:
    def test_build_report(self) -> None:
        from apps.automation.management.commands.bench_http import _build_report

        timings = [10.0, 20.0, 30.0, 40.0, 50.0]
        report = _build_report("http://test.com", "GET", 5, 1, {200: 5}, timings)
        assert report["url"] == "http://test.com"
        assert report["method"] == "GET"
        assert report["requests"] == 5
        assert report["latency_ms"]["min"] == 10.0
        assert report["latency_ms"]["max"] == 50.0

    def test_build_report_empty(self) -> None:
        from apps.automation.management.commands.bench_http import _build_report

        report = _build_report("http://test.com", "GET", 0, 1, {}, [])
        assert report["latency_ms"]["min"] is None


class TestBenchHttpParseFunctions:
    def test_parse_headers_valid(self) -> None:
        from apps.automation.management.commands.bench_http import _parse_headers

        result = _parse_headers(["Content-Type: application/json", "Authorization: Bearer tok"])
        assert result["Content-Type"] == "application/json"
        assert result["Authorization"] == "Bearer tok"

    def test_parse_headers_invalid_raises(self) -> None:
        from apps.automation.management.commands.bench_http import _parse_headers

        with pytest.raises(CommandError, match="header"):
            _parse_headers(["no-colon"])

    def test_parse_json_body_none(self) -> None:
        from apps.automation.management.commands.bench_http import _parse_json_body

        assert _parse_json_body(None) is None

    def test_parse_json_body_valid(self) -> None:
        from apps.automation.management.commands.bench_http import _parse_json_body

        result = _parse_json_body('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_body_invalid_raises(self) -> None:
        from apps.automation.management.commands.bench_http import _parse_json_body

        with pytest.raises(CommandError, match="JSON"):
            _parse_json_body("not json")
