"""Tests for apps/automation/checks.py — check_scraper_dependencies."""

from __future__ import annotations

import builtins
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCheckScraperDependencies:
    """check_scraper_dependencies 单元测试。"""

    def _call(self, app_configs: object | None = None) -> list:
        from apps.automation.checks import check_scraper_dependencies

        return check_scraper_dependencies(app_configs)

    def test_no_errors_when_all_configured(self) -> None:
        """Playwright 已安装 + ENCRYPTION_KEY 已设置 + MEDIA_ROOT 存在 => 0 errors。"""
        with patch("apps.automation.checks.settings", SimpleNamespace(
            SCRAPER_ENCRYPTION_KEY="secret-key",
            MEDIA_ROOT="/tmp/media",
        )):
            result = self._call()
            assert result == []

    def test_warning_when_playwright_missing(self) -> None:
        """Playwright 未安装 => 包含 W002 警告。"""
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "playwright":
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with patch("apps.automation.checks.settings", SimpleNamespace(
            SCRAPER_ENCRYPTION_KEY="key",
            MEDIA_ROOT="/tmp",
        )):
            with patch("builtins.__import__", side_effect=mock_import):
                result = self._call()
                ids = [m.id for m in result]
                assert "automation.W002" in ids

    def test_warning_when_encryption_key_missing(self) -> None:
        """SCRAPER_ENCRYPTION_KEY 未配置 => 包含 W001 警告。"""
        with patch("apps.automation.checks.settings", SimpleNamespace(
            MEDIA_ROOT="/tmp",
        )):
            result = self._call()
            ids = [m.id for m in result]
            assert "automation.W001" in ids

    def test_error_when_media_root_missing(self) -> None:
        """MEDIA_ROOT 未配置 => 包含 E002 错误。"""
        with patch("apps.automation.checks.settings", SimpleNamespace(
            SCRAPER_ENCRYPTION_KEY="key",
        )):
            result = self._call()
            ids = [m.id for m in result]
            assert "automation.E002" in ids

    def test_returns_list(self) -> None:
        """返回类型始终是 list。"""
        with patch("apps.automation.checks.settings", SimpleNamespace(
            SCRAPER_ENCRYPTION_KEY="k",
            MEDIA_ROOT="/tmp",
        )):
            result = self._call()
            assert isinstance(result, list)
