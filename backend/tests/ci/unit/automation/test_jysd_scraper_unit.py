"""JysdCourtScraper 非浏览器部分测试。"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, PropertyMock

from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper


class TestJysdCourtScraper:
    """JysdCourtScraper 测试（不涉及浏览器交互）。"""

    def _make_scraper(self) -> JysdCourtScraper:
        scraper = JysdCourtScraper.__new__(JysdCourtScraper)
        scraper.task = MagicMock()
        scraper.page = None
        return scraper

    # ─── _mask_phone ───

    def test_mask_phone_normal(self) -> None:
        assert JysdCourtScraper._mask_phone("13612340615") == "136****0615"

    def test_mask_phone_short(self) -> None:
        assert JysdCourtScraper._mask_phone("123") == "***"

    def test_mask_phone_7_chars(self) -> None:
        assert JysdCourtScraper._mask_phone("1234567") == "123****4567"

    # ─── _get_lawyer_phones ───

    def test_get_lawyer_phones_from_config(self) -> None:
        scraper = self._make_scraper()
        scraper.task.config = {"jysd_lawyer_phones": ["13612340615", " 13800138000 "]}
        phones = scraper._get_lawyer_phones()
        assert len(phones) == 2
        assert phones[0] == "13612340615"
        assert phones[1] == "13800138000"

    def test_get_lawyer_phones_empty_config(self) -> None:
        scraper = self._make_scraper()
        scraper.task.config = {}
        assert scraper._get_lawyer_phones() == []

    def test_get_lawyer_phones_non_list(self) -> None:
        scraper = self._make_scraper()
        scraper.task.config = {"jysd_lawyer_phones": "not_a_list"}
        assert scraper._get_lawyer_phones() == []

    def test_get_lawyer_phones_non_dict_config(self) -> None:
        scraper = self._make_scraper()
        scraper.task.config = "invalid"
        assert scraper._get_lawyer_phones() == []

    def test_get_lawyer_phones_with_empty_strings(self) -> None:
        scraper = self._make_scraper()
        scraper.task.config = {"jysd_lawyer_phones": ["13612340615", "", "  ", "13800138000"]}
        phones = scraper._get_lawyer_phones()
        assert len(phones) == 2

    # ─── _safe_filename ───

    def test_safe_filename_normal(self) -> None:
        assert JysdCourtScraper._safe_filename("判决书.pdf") == "判决书.pdf"

    def test_safe_filename_special_chars(self) -> None:
        result = JysdCourtScraper._safe_filename('file<>:"|?*name.pdf')
        assert "<" not in result
        assert ">" not in result

    def test_safe_filename_newlines(self) -> None:
        result = JysdCourtScraper._safe_filename("file\nname\r.pdf")
        assert "\n" not in result

    def test_safe_filename_empty(self) -> None:
        result = JysdCourtScraper._safe_filename("")
        assert result.startswith("jysd_")
        assert result.endswith(".pdf")

    # ─── _check_login_result ───

    def test_check_login_result_no_iframe(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        scraper.page.frames = []
        assert scraper._check_login_result() is False

    def test_check_login_result_middle_page(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/middlePagePc"
        scraper.page.frames = [iframe]
        assert scraper._check_login_result() is True

    def test_check_login_result_still_login(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/checkLoginPc"
        scraper.page.frames = [iframe]
        assert scraper._check_login_result() is False

    def test_check_login_result_home_page(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/home"
        scraper.page.frames = [iframe]
        assert scraper._check_login_result() is True

    def test_check_login_result_middle_page_generic(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/middlePage"
        scraper.page.frames = [iframe]
        assert scraper._check_login_result() is True

    def test_check_login_result_unknown_url(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/unknown"
        scraper.page.frames = [iframe]
        assert scraper._check_login_result() is False

    # ─── _get_sifayun_iframe ───

    def test_get_sifayun_iframe_found(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        iframe = MagicMock()
        iframe.url = "https://sd5.sifayun.com/page"
        scraper.page.frames = [MagicMock(url="other"), iframe]
        result = scraper._get_sifayun_iframe()
        assert result is iframe

    def test_get_sifayun_iframe_not_found(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        scraper.page.frames = [MagicMock(url="https://other.com")]
        result = scraper._get_sifayun_iframe()
        assert result is None

    def test_get_sifayun_iframe_exception(self) -> None:
        scraper = self._make_scraper()
        scraper.page = MagicMock()
        type(scraper.page).frames = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        result = scraper._get_sifayun_iframe()
        assert result is None
