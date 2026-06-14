"""Tests for automation.utils.text_utils and automation.checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestTextUtilsNormalizeCaseNumber:
    """Cover TextUtils.normalize_case_number branches."""

    def _fn(self):
        from apps.automation.utils.text_utils import TextUtils
        return TextUtils.normalize_case_number

    def test_empty_string(self):
        assert self._fn()("") == ""

    def test_none_input(self):
        assert self._fn()(None) == ""

    def test_standardize_parens(self):
        result = self._fn()("(2025)粤01民初1号")
        assert "（" in result
        assert "）" in result

    def test_square_brackets(self):
        result = self._fn()("[2025]粤01民初1号")
        assert "（" in result
        assert "）" in result

    def test_full_width_parens_passthrough(self):
        result = self._fn()("（2025）粤01民初1号")
        assert result == "（2025）粤01民初1号"

    def test_removes_spaces(self):
        result = self._fn()("（2025）粤 01 民初 1 号")
        assert " " not in result

    def test_removes_full_width_space(self):
        result = self._fn()("（2025）粤　01民初1号")
        assert "　" not in result

    def test_appends_hao(self):
        result = self._fn()("（2025）粤01民初1")
        assert result.endswith("号")

    def test_already_has_hao(self):
        result = self._fn()("（2025）粤01民初1号")
        assert result.endswith("号")
        # Should not double-append
        assert not result.endswith("号号")


class TestTextUtilsCleanText:
    """Cover TextUtils.clean_text branches."""

    def _fn(self):
        from apps.automation.utils.text_utils import TextUtils
        return TextUtils.clean_text

    def test_empty_string(self):
        assert self._fn()("") == ""

    def test_none_input(self):
        assert self._fn()(None) == ""

    def test_removes_control_chars(self):
        text = "hello\x00world\x01test"
        result = self._fn()(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "hello" in result

    def test_merges_whitespace(self):
        text = "hello   world\t\ttest\n\nfoo"
        result = self._fn()(text)
        assert result == "hello world test foo"

    def test_strips_leading_trailing(self):
        text = "  hello world  "
        result = self._fn()(text)
        assert result == "hello world"

    def test_normal_text_unchanged(self):
        text = "normal text"
        result = self._fn()(text)
        assert result == "normal text"


class TestTextUtilsExtractCaseNumbers:
    """Cover TextUtils.extract_case_numbers branches."""

    def _fn(self):
        from apps.automation.utils.text_utils import TextUtils
        return TextUtils.extract_case_numbers

    def test_empty_text(self):
        assert self._fn()("") == []

    def test_no_case_numbers(self):
        assert self._fn()("普通文本，没有案号") == []

    def test_single_case_number(self):
        text = "案件（2025）粤01民初12345号"
        result = self._fn()(text)
        assert len(result) >= 1

    def test_dedup_case_numbers(self):
        text = "（2025）粤01民初1号 和 （2025）粤01民初1号"
        result = self._fn()(text)
        assert len(result) == 1

    def test_multiple_case_numbers(self):
        text = "（2025）粤01民初1号（2024）粤01民初2号"
        result = self._fn()(text)
        assert len(result) >= 1

    def test_excludes_date_format(self):
        text = "2025年12月17号"
        result = self._fn()(text)
        # Date patterns should be excluded
        for cn in result:
            assert "年" not in cn


class TestCheckScraperDependencies:
    """Cover check_scraper_dependencies branches."""

    def test_no_errors(self):
        from apps.automation.checks import check_scraper_dependencies

        with patch.dict("sys.modules", {"playwright": MagicMock()}):
            with patch("apps.automation.checks.settings") as mock_settings:
                mock_settings.SCRAPER_ENCRYPTION_KEY = "test_key"
                mock_settings.MEDIA_ROOT = "/tmp/media"
                result = check_scraper_dependencies(None)
        assert len(result) == 0

    def test_playwright_not_installed(self):
        from apps.automation.checks import check_scraper_dependencies

        with patch.dict("sys.modules", {"playwright": None}):
            with patch("apps.automation.checks.settings") as mock_settings:
                mock_settings.SCRAPER_ENCRYPTION_KEY = "test_key"
                mock_settings.MEDIA_ROOT = "/tmp/media"
                result = check_scraper_dependencies(None)
        assert any("Playwright" in str(msg) for msg in result)

    def test_no_encryption_key(self):
        from apps.automation.checks import check_scraper_dependencies

        with patch.dict("sys.modules", {"playwright": MagicMock()}):
            with patch("apps.automation.checks.settings") as mock_settings:
                mock_settings.SCRAPER_ENCRYPTION_KEY = None
                mock_settings.MEDIA_ROOT = "/tmp/media"
                result = check_scraper_dependencies(None)
        assert any("SCRAPER_ENCRYPTION_KEY" in str(msg) for msg in result)

    def test_no_media_root(self):
        from apps.automation.checks import check_scraper_dependencies

        with patch.dict("sys.modules", {"playwright": MagicMock()}):
            with patch("apps.automation.checks.settings") as mock_settings:
                mock_settings.SCRAPER_ENCRYPTION_KEY = "test_key"
                # Remove MEDIA_ROOT attribute
                del mock_settings.MEDIA_ROOT
                result = check_scraper_dependencies(None)
        assert any("MEDIA_ROOT" in str(msg) for msg in result)
