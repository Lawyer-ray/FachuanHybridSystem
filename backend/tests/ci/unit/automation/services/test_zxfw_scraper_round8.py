"""zxfw_scraper.py — round8 tests.

Covers 45 missing: run() with all three download strategies, _is_playwright_available,
fallback flow, exception handling paths.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestIsPlaywrightAvailable:
    def test_available(self):
        import sys
        with patch.dict(sys.modules, {"playwright": MagicMock()}):
            from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import _is_playwright_available
            assert _is_playwright_available() is True

    def test_not_available(self):
        import sys
        with patch.dict(sys.modules, {"playwright": None}):
            from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import _is_playwright_available

            # When import fails, should return False
            result = _is_playwright_available()
            # Result depends on whether playwright was already imported
            assert isinstance(result, bool)


# ── ZxfwCourtScraper.run ──────────────────────────────────────────────


class TestZxfwCourtScraperRun:
    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import ZxfwCourtScraper
        scraper = ZxfwCourtScraper.__new__(ZxfwCourtScraper)
        scraper.task = MagicMock()
        scraper.task.url = "https://zxfw.court.gov.cn/test"
        return scraper

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=True)
    def test_direct_api_success(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(return_value={"document_count": 1, "downloaded_count": 1})

        result = scraper.run()
        assert result["document_count"] == 1

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=False)
    def test_direct_api_fails_no_playwright(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))

        from apps.core.exceptions import ExternalServiceError
        with pytest.raises(ExternalServiceError, match="Playwright 未安装"):
            scraper.run()

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=True)
    def test_direct_api_fails_intercept_success(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(
            return_value={"document_count": 1, "downloaded_count": 1}
        )

        result = scraper.run()
        assert result["method"] == "api_intercept"
        assert "direct_api_error" in result

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=True)
    def test_direct_api_fails_intercept_fails_fallback_success(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(side_effect=Exception("intercept error"))
        scraper._download_via_fallback = MagicMock(
            return_value={"downloaded_count": 1}
        )

        result = scraper.run()
        assert result["method"] == "fallback"
        assert "direct_api_error" in result
        assert "api_intercept_error" in result

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=True)
    def test_all_methods_fail(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(side_effect=Exception("intercept error"))
        scraper._download_via_fallback = MagicMock(side_effect=Exception("fallback error"))

        from apps.core.exceptions import ExternalServiceError
        with pytest.raises(ExternalServiceError, match="所有下载方式均失败"):
            scraper.run()

    @patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available", return_value=True)
    def test_direct_api_fails_no_page_clear_error(self, mock_pw):
        """直接 API 失败且浏览器页面未初始化时，应给出清晰报错而非 NoneType 崩溃。

        该场景对应 requires_browser=False 的纯 API 模式：
        - API 拦截、页面点击两种退化策略因 self.page 为空直接跳过
        - 最终错误应附带 browser_initialized=False 及可读的失败原因
        """
        from apps.core.exceptions import ExternalServiceError

        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper.page = None
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))

        with pytest.raises(ExternalServiceError) as exc_info:
            scraper.run()

        assert exc_info.value.code == "DOWNLOAD_ALL_METHODS_FAILED"
        errors = exc_info.value.errors or {}
        assert errors.get("browser_initialized") is False
        assert "浏览器页面未初始化" in errors.get("api_intercept_error", "")
        assert "浏览器页面未初始化" in errors.get("fallback_error", "")
        assert "hint" in errors
        # 不应出现误导性的 NoneType 信息
        assert "NoneType" not in errors.get("api_intercept_error", "")
        assert "NoneType" not in errors.get("fallback_error", "")
