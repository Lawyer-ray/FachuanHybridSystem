from types import SimpleNamespace

from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper
from apps.core.path import Path


def _make_scraper(tmp_path, direct_api=None, api_intercept=None, fallback=None):
    class DummyScraper(CourtDocumentScraper):
        def __init__(self):
            self.task = SimpleNamespace(
                url="https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3",
                case_id=None,
                id=1,
            )

        def _prepare_download_dir(self):
            return Path(str(tmp_path))

        def _download_via_direct_api(self, url, download_dir):
            if direct_api is None:
                raise ValueError("direct_api_failed")
            return direct_api

        def _download_via_api_intercept(self, download_dir):
            if api_intercept is None:
                raise ValueError("api_intercept_failed")
            return api_intercept

        def _download_via_api_intercept_with_navigation(self, download_dir):
            return self._download_via_api_intercept(download_dir)

        def _download_via_fallback(self, download_dir):
            if fallback is None:
                raise ValueError("fallback_failed")
            return fallback

    return DummyScraper()


def test_attempts_direct_api_success(tmp_path):
    scraper = _make_scraper(tmp_path, direct_api={"document_count": 1, "downloaded_count": 1})
    result = scraper._download_zxfw_court(scraper.task.url)

    assert result["attempts"] == [
        {
            "method": "direct_api",
            "success": True,
            "elapsed_ms": result["attempts"][0]["elapsed_ms"],
            "document_count": 1,
            "downloaded_count": 1,
        }
    ]


def test_attempts_fallback_success_after_failures(tmp_path):
    scraper = _make_scraper(tmp_path, fallback={"document_count": 2, "downloaded_count": 1})
    result = scraper._download_zxfw_court(scraper.task.url)

    methods = [attempt["method"] for attempt in result["attempts"]]
    statuses = [attempt["success"] for attempt in result["attempts"]]

    assert methods == ["direct_api", "api_intercept", "fallback"]
    assert statuses == [False, False, True]
