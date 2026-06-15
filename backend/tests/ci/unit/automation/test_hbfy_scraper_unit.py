"""hbfy_scraper.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestHbfyExtractPublicMsgCode:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        scraper.task = SimpleNamespace(url="", config={})
        return scraper

    def test_extracts_msg_code(self):
        scraper = self._make_scraper()
        result = scraper._extract_public_msg_code("http://dzsd.hbfy.gov.cn/hb/msg=ABC123XYZ")
        assert result == "ABC123XYZ"

    def test_empty_when_no_match(self):
        scraper = self._make_scraper()
        assert scraper._extract_public_msg_code("http://example.com/page") == ""


class TestHbfyPublicNeedCaptcha:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_needs_captcha(self):
        scraper = self._make_scraper()
        assert scraper._public_need_captcha({"isNeedCaptcha": "Y"}) is True

    def test_no_captcha_needed(self):
        scraper = self._make_scraper()
        assert scraper._public_need_captcha({"isNeedCaptcha": "N"}) is False

    def test_missing_field_defaults_no(self):
        scraper = self._make_scraper()
        assert scraper._public_need_captcha({}) is False


class TestHbfyPublicDocList:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_dict_wrapped_in_list(self):
        scraper = self._make_scraper()
        result = scraper._public_doc_list({"docList": {"name": "doc1"}})
        assert len(result) == 1
        assert result[0]["name"] == "doc1"

    def test_list_returned_as_is(self):
        scraper = self._make_scraper()
        result = scraper._public_doc_list({"docList": [{"name": "a"}, {"name": "b"}]})
        assert len(result) == 2

    def test_none_returns_empty(self):
        scraper = self._make_scraper()
        assert scraper._public_doc_list({}) == []


class TestHbfyPublicHasDownloadableDocs:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_has_download_path(self):
        scraper = self._make_scraper()
        sms = {"docList": [{"downloadPath": "/files/doc.pdf"}]}
        assert scraper._public_has_downloadable_docs(sms) is True

    def test_empty_download_path(self):
        scraper = self._make_scraper()
        sms = {"docList": [{"downloadPath": ""}]}
        assert scraper._public_has_downloadable_docs(sms) is False


class TestHbfyExtractAccountCredentials:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_extracts_account_and_password(self):
        scraper = self._make_scraper()
        content = "您的送达文书已到达。账号 42010012345678901，默认密码：Abc12345"
        account, password = scraper._extract_account_credentials_from_content(content)
        assert account == "42010012345678901"
        assert password == "Abc12345"

    def test_no_match_returns_empty(self):
        scraper = self._make_scraper()
        account, password = scraper._extract_account_credentials_from_content("无关内容")
        assert account == ""
        assert password == ""


class TestHbfySafeFilename:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_removes_special_chars(self):
        scraper = self._make_scraper()
        result = scraper._safe_filename("文件*名?.pdf")
        assert "*" not in result
        assert "?" not in result

    def test_empty_fallback(self):
        scraper = self._make_scraper()
        result = scraper._safe_filename("")
        assert result.startswith("dzsd_")


class TestHbfyEncodeUserCode:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_base64_no_padding(self):
        scraper = self._make_scraper()
        result = scraper._encode_user_code("12345")
        assert "=" not in result
        assert "+" not in result
        assert "/" not in result


class TestHbfyExtractDownloadCandidates:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        return HbfyCourtScraper.__new__(HbfyCourtScraper)

    def test_extracts_download_link(self):
        scraper = self._make_scraper()
        html = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/files/doc.pdf">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) >= 1

    def test_skips_empty_path(self):
        scraper = self._make_scraper()
        html = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) == 0


class TestHbfyGuessFilename:

    def _make_scraper(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        return scraper

    def test_content_disposition_utf8(self):
        scraper = self._make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Disposition": "filename*=UTF-8''%E6%96%87%E4%B9%A6.pdf"}
        result = scraper._guess_filename(resp, "http://example.com/file", "title")
        assert "文书" in result

    def test_content_disposition_regular(self):
        scraper = self._make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Disposition": 'filename="test.pdf"'}
        result = scraper._guess_filename(resp, "http://example.com/file", "title")
        assert "test.pdf" in result

    def test_fallback_to_content_type(self):
        scraper = self._make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/pdf"}
        result = scraper._guess_filename(resp, "http://example.com/", "文书标题")
        assert result.endswith(".pdf")


class TestHbfyRun:

    def test_raises_for_unknown_url(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        scraper.task = SimpleNamespace(url="http://example.com/unknown")
        with pytest.raises(ValueError, match="不支持"):
            scraper.run()
