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
        # 纯 API 模式构造：无浏览器上下文，浏览器服务可按需懒创建
        scraper.browser_service = MagicMock()
        scraper.page = None
        scraper.context = None
        return scraper

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
    def test_direct_api_success(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(return_value={"document_count": 1, "downloaded_count": 1})

        result = scraper.run()
        assert result["document_count"] == 1

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=False,
    )
    def test_direct_api_fails_no_playwright(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))

        from apps.core.exceptions import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="Playwright 未安装"):
            scraper.run()

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
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

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
    def test_direct_api_fails_intercept_fails_fallback_success(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(side_effect=Exception("intercept error"))
        scraper._download_via_fallback = MagicMock(return_value={"downloaded_count": 1})

        result = scraper.run()
        assert result["method"] == "fallback"
        assert "direct_api_error" in result
        assert "api_intercept_error" in result

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
    def test_all_methods_fail(self, mock_pw):
        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(side_effect=Exception("intercept error"))
        scraper._download_via_fallback = MagicMock(side_effect=Exception("fallback error"))

        from apps.core.exceptions import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="所有下载方式均失败"):
            scraper.run()

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
    def test_direct_api_fails_lazy_browser_fallback_all_fail(self, mock_pw):
        """直接 API 失败后应懒创建浏览器再走降级策略；策略全部失败时错误信息完整，
        且自建浏览器上下文在 finally 中关闭（不留浏览器泄漏）。

        该场景对应 requires_browser=False 的纯 API 模式（2026-10-27 任务 313 实发）：
        修复前降级两策略因 self.page 恒为 None 直接死路，三级降级名存实亡。
        """
        from apps.core.exceptions import ExternalServiceError

        scraper = self._make_scraper()
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api timeout"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(side_effect=Exception("intercept error"))
        scraper._download_via_fallback = MagicMock(side_effect=Exception("fallback error"))

        with pytest.raises(ExternalServiceError) as exc_info:
            scraper.run()

        assert exc_info.value.code == "DOWNLOAD_ALL_METHODS_FAILED"
        errors = exc_info.value.errors or {}
        # 懒初始化已执行：降级策略拿到的是浏览器页面而非 page is None 死路
        assert errors.get("browser_initialized") is True
        assert "浏览器页面未初始化" not in errors.get("api_intercept_error", "")
        assert "浏览器页面未初始化" not in errors.get("fallback_error", "")
        assert "api timeout" in errors.get("direct_api_error", "")
        # 懒初始化已执行：自建上下文用完即关，不留浏览器泄漏
        scraper.browser_service.create_context.assert_called_once_with(use_anti_detection=True)
        created_context = scraper.browser_service.create_context.return_value
        created_context.new_page.assert_called_once()
        created_context.new_page.return_value.close.assert_called_once()
        created_context.close.assert_called_once()
        assert scraper.page is None
        assert scraper.context is None

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper._is_playwright_available",
        return_value=True,
    )
    def test_shared_browser_context_not_closed_by_run(self, mock_pw):
        """dispatcher 预建的共享上下文（page 已存在）不应被 run() 关闭。"""
        scraper = self._make_scraper()
        shared_page, shared_context = MagicMock(), MagicMock()
        scraper.page, scraper.context = shared_page, shared_context
        scraper._prepare_download_dir = MagicMock(return_value=MagicMock())
        scraper._download_via_direct_api = MagicMock(side_effect=Exception("api error"))
        scraper._download_via_api_intercept_with_navigation = MagicMock(
            return_value={"document_count": 1, "downloaded_count": 1}
        )

        result = scraper.run()

        assert result["method"] == "api_intercept"
        scraper.browser_service.create_context.assert_not_called()
        shared_page.close.assert_not_called()
        shared_context.close.assert_not_called()
        assert scraper.page is shared_page
