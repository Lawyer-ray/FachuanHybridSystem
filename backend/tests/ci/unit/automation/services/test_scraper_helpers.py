"""Tests for court document scrapers - URL, filename, config parsing."""

import re
import time
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ============================================================
# main.py - CourtDocumentScraper URL resolution
# ============================================================

class TestCourtDocumentScraperResolve:
    """Tests for URL-based scraper class resolution."""

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.main import CourtDocumentScraper
        task = MagicMock()
        task.url = "https://example.com"
        task.case_id = None
        task.id = 1
        scraper = CourtDocumentScraper.__new__(CourtDocumentScraper)
        scraper.task = task
        scraper.debug_info = {}
        scraper._document_service = None
        scraper._scraper = None
        scraper.context = None
        scraper.page = None
        scraper.browser = None
        return scraper

    def test_extract_host(self):
        scraper = self._make_scraper()
        assert scraper._extract_host("https://zxfw.court.gov.cn/path") == "zxfw.court.gov.cn"
        assert scraper._extract_host("https://sd.gdems.com/path") == "sd.gdems.com"

    def test_host_equals_or_subdomain_exact(self):
        scraper = self._make_scraper()
        assert scraper._host_equals_or_subdomain("zxfw.court.gov.cn", "zxfw.court.gov.cn") is True

    def test_host_equals_or_subdomain_subdomain(self):
        scraper = self._make_scraper()
        assert scraper._host_equals_or_subdomain("sub.zxfw.court.gov.cn", "zxfw.court.gov.cn") is True

    def test_host_equals_or_subdomain_no_match(self):
        scraper = self._make_scraper()
        assert scraper._host_equals_or_subdomain("other.court.gov.cn", "zxfw.court.gov.cn") is False

    def test_resolve_zxfw_scraper(self):
        scraper = self._make_scraper()
        scraper.task.url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/pagesajkj/app/wssd/index"
        result = scraper._resolve_scraper_class(scraper.task.url)
        from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import ZxfwCourtScraper
        assert result is ZxfwCourtScraper

    @patch("apps.automation.services.scraper.scrapers.court_document.main._is_playwright_available", return_value=False)
    def test_resolve_unsupported_url_raises(self, mock_pw):
        scraper = self._make_scraper()
        with pytest.raises(ValueError, match="不支持的链接格式"):
            scraper._resolve_scraper_class("https://unknown-platform.com/doc")

    @patch("apps.automation.services.scraper.scrapers.court_document.main._is_playwright_available", return_value=False)
    def test_resolve_ensures_playwright_for_gdems(self, mock_pw):
        scraper = self._make_scraper()
        scraper.task.url = "https://sd.gdems.com/page"
        with pytest.raises(RuntimeError, match="Playwright"):
            scraper._resolve_scraper_class(scraper.task.url)


# ============================================================
# sfdw_scraper.py - _safe_filename, config parsing
# ============================================================

class TestSfdwScraperHelpers:
    """Tests for SfdwCourtScraper helper methods."""

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.sfdw_scraper import SfdwCourtScraper
        task = MagicMock()
        task.config = {}
        task.url = "https://sfpt.cdfy12368.gov.cn/test"
        task.id = 1
        task.case_id = None
        scraper = SfdwCourtScraper.__new__(SfdwCourtScraper)
        scraper.task = task
        scraper.debug_info = {}
        return scraper

    def test_safe_filename_removes_illegal_chars(self):
        from apps.automation.services.scraper.scrapers.court_document.sfdw_scraper import SfdwCourtScraper
        result = SfdwCourtScraper._safe_filename('test:file/name*.pdf')
        assert ':' not in result
        assert '/' not in result
        assert '*' not in result
        assert result.endswith('.pdf')

    def test_safe_filename_non_pdf_extension(self):
        from apps.automation.services.scraper.scrapers.court_document.sfdw_scraper import SfdwCourtScraper
        result = SfdwCourtScraper._safe_filename('test.doc')
        assert result == 'test.doc'

    def test_get_verification_code_from_config(self):
        scraper = self._make_scraper()
        scraper.task.config = {"sfdw_verification_code": "123456"}
        assert scraper._get_verification_code() == "123456"

    def test_get_verification_code_empty(self):
        scraper = self._make_scraper()
        scraper.task.config = {}
        assert scraper._get_verification_code() == ""

    def test_get_phone_tail6_manual_first(self):
        scraper = self._make_scraper()
        scraper.task.config = {
            "sfdw_phone_tail6": "00000000000",
            "sfdw_phone_tail6_candidates": ["00000000001"],
        }
        result = scraper._get_phone_tail6_candidates()
        assert len(result) == 2
        assert result[0] == "000000"  # last 6 digits of 00000000000
        assert result[1] == "000001"  # last 6 digits of 00000000001

    def test_get_phone_tail6_deduplicates(self):
        scraper = self._make_scraper()
        scraper.task.config = {
            "sfdw_phone_tail6": "00000000000",
            "sfdw_phone_tail6_candidates": ["01000000000"],
        }
        result = scraper._get_phone_tail6_candidates()
        assert len(result) == 1

    def test_get_phone_tail6_empty(self):
        scraper = self._make_scraper()
        scraper.task.config = {}
        assert scraper._get_phone_tail6_candidates() == []


# ============================================================
# jysd_scraper.py - _mask_phone, _safe_filename
# ============================================================

class TestJysdScraperHelpers:
    def test_mask_phone_normal(self):
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper
        assert JysdCourtScraper._mask_phone("00000000000") == "000****0000"

    def test_mask_phone_short(self):
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper
        assert JysdCourtScraper._mask_phone("123") == "***"

    def test_safe_filename(self):
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper
        result = JysdCourtScraper._safe_filename("test/file.pdf")
        assert "/" not in result

    def test_safe_filename_chinese_chars(self):
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper
        result = JysdCourtScraper._safe_filename("民事判决书.pdf")
        assert result == "民事判决书.pdf"


# ============================================================
# gdems_scraper.py - _build_no_document_result
# ============================================================

class TestGdemsScraperHelpers:
    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.gdems_scraper import GdemsCourtScraper
        task = MagicMock()
        task.url = "https://sd.gdems.com/test"
        task.id = 1
        task.case_id = None
        scraper = GdemsCourtScraper.__new__(GdemsCourtScraper)
        scraper.task = task
        scraper.debug_info = {}
        scraper.page = None
        return scraper

    def test_build_no_document_result(self):
        scraper = self._make_scraper()
        scraper._extract_canvas_notification = MagicMock(return_value="test notification")
        scraper._save_page_state = MagicMock()
        result = scraper._build_no_document_result("screenshot_path")
        assert result["file_count"] == 0
        assert result["source"] == "sd.gdems.com"
        assert result["notification_text"] == "test notification"
        assert result["message"] == "书记员尚未放置文书文件，确定按钮无法点击，无文书可下载"


# ============================================================
# _zxfw_intercept_mixin.py - _process_api_data_and_download
# ============================================================

class TestZxfwInterceptMixin:
    def test_process_api_data_none_raises(self):
        from apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin import (
            ZxfwInterceptMixin,
        )
        mixin = ZxfwInterceptMixin()
        with pytest.raises(ValueError, match="API 拦截超时"):
            mixin._process_api_data_and_download(None, Path("/tmp"))

    def test_process_api_data_non_dict_raises(self):
        from apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin import (
            ZxfwInterceptMixin,
        )
        mixin = ZxfwInterceptMixin()
        with pytest.raises(ValueError, match="API 响应格式错误"):
            mixin._process_api_data_and_download("not a dict", Path("/tmp"))

    def test_process_api_data_missing_data_raises(self):
        from apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin import (
            ZxfwInterceptMixin,
        )
        mixin = ZxfwInterceptMixin()
        with pytest.raises(ValueError, match="缺少 data 字段"):
            mixin._process_api_data_and_download({"other": "val"}, Path("/tmp"))

    def test_process_api_data_empty_data_raises(self):
        from apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin import (
            ZxfwInterceptMixin,
        )
        mixin = ZxfwInterceptMixin()
        with pytest.raises(ValueError, match="没有文书数据"):
            mixin._process_api_data_and_download({"data": []}, Path("/tmp"))
