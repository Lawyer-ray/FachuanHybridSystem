"""court_zxfw.py 单元测试 — Playwright 浏览器交互。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestCourtZxfwService:

    def _make_service(self):
        """创建一个带 mock page/context 的 CourtZxfwService。"""
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
        page = MagicMock()
        page.url = "https://zxfw.court.gov.cn/zxfw/"
        context = MagicMock()
        captcha = MagicMock()
        captcha.recognize_from_element.return_value = "abcd"
        cookie_service = MagicMock()
        cookie_service.load.return_value = False
        token_service = MagicMock()
        service = CourtZxfwService(
            page=page,
            context=context,
            captcha_recognizer=captcha,
            token_service=token_service,
            cookie_service=cookie_service,
        )
        return service

    def test_init_sets_defaults(self):
        service = self._make_service()
        assert service.is_logged_in is False
        assert service.site_name == "court_zxfw"

    def test_extract_token_from_body_data_token(self):
        service = self._make_service()
        body = {"data": {"token": "abc123"}}
        assert service._extract_token_from_body(body) == "abc123"

    def test_extract_token_from_body_access_token(self):
        service = self._make_service()
        body = {"data": {"access_token": "xyz789"}}
        assert service._extract_token_from_body(body) == "xyz789"

    def test_extract_token_from_body_top_level(self):
        service = self._make_service()
        body = {"token": "top_level_token"}
        assert service._extract_token_from_body(body) == "top_level_token"

    def test_extract_token_returns_none_for_empty(self):
        service = self._make_service()
        assert service._extract_token_from_body({}) is None
        assert service._extract_token_from_body({"data": {}}) is None

    def test_extract_token_from_result_wrapper(self):
        service = self._make_service()
        body = {"result": {"accessToken": "bearer_token"}}
        assert service._extract_token_from_body(body) == "bearer_token"

    def test_is_network_error_connection_error(self):
        service = self._make_service()
        assert service._is_network_error(ConnectionError()) is True

    def test_is_network_error_timeout(self):
        service = self._make_service()
        assert service._is_network_error(TimeoutError()) is True

    def test_is_network_error_socket_gaierror(self):
        import socket
        service = self._make_service()
        assert service._is_network_error(socket.gaierror()) is True

    def test_is_network_error_generic_exception(self):
        service = self._make_service()
        assert service._is_network_error(ValueError("normal error")) is False

    def test_is_network_error_playwright_network(self):
        service = self._make_service()
        assert service._is_network_error(Exception("ERR_INTERNET_DISCONNECTED")) is True
        assert service._is_network_error(Exception("err_name_not_resolved")) is True

    def test_get_cookie_path(self):
        service = self._make_service()
        path = service._get_cookie_path("user@example.com")
        assert "user_at_example.com" in path
        assert path.startswith("cookies/court_zxfw/")

    def test_check_login_success_redirect(self):
        service = self._make_service()
        service.page.url = "https://zxfw.court.gov.cn/zxfw/#/home"
        assert service._check_login_success() is True

    def test_check_login_still_on_login(self):
        service = self._make_service()
        service.page.url = "https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index"
        service.page.locator.return_value.count.return_value = 0
        assert service._check_login_success() is False

    def test_file_case_raises_when_not_logged_in(self):
        service = self._make_service()
        with pytest.raises(ValueError, match="请先登录"):
            service.file_case({})

    def test_query_case_raises_when_not_logged_in(self):
        service = self._make_service()
        with pytest.raises(ValueError, match="请先登录"):
            service.query_case("案号")

    def test_download_document_raises_when_not_logged_in(self):
        service = self._make_service()
        with pytest.raises(ValueError, match="请先登录"):
            service.download_document("http://example.com")

    def test_try_http_login_returns_none_when_plugin_missing(self):
        service = self._make_service()
        with patch.dict("sys.modules", {"apps.automation.services.scraper.sites.court_zxfw_login_private": None}):
            result = service._try_http_login("user", "pass", 3)
        # 返回 None 表示插件不可用
        assert result is None

    def test_login_raises_network_error(self):
        service = self._make_service()
        service._cookie_service.load.return_value = False
        service._try_http_login = MagicMock(return_value=None)
        service._goto_with_retry = MagicMock(side_effect=ConnectionError("网络断开"))
        with pytest.raises(ConnectionError, match="网络连接异常"):
            service.login("user", "pass", max_captcha_retries=1)


class TestCourtZxfwGotoWithRetry:

    def test_retries_on_network_error(self):
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
        page = MagicMock()
        page.goto.side_effect = [ConnectionError("timeout"), None]
        page.url = "https://example.com"
        context = MagicMock()
        service = CourtZxfwService(page=page, context=context, captcha_recognizer=MagicMock(), cookie_service=MagicMock())
        service._goto_with_retry("https://example.com", max_attempts=2)
        assert page.goto.call_count == 2

    def test_raises_non_network_error_immediately(self):
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
        page = MagicMock()
        page.goto.side_effect = ValueError("some error")
        context = MagicMock()
        service = CourtZxfwService(page=page, context=context, captcha_recognizer=MagicMock(), cookie_service=MagicMock())
        with pytest.raises(ValueError):
            service._goto_with_retry("https://example.com", max_attempts=3)


class TestMakeResponseHandler:

    def test_captures_token_from_login_response(self):
        import json
        service = TestCourtZxfwService._make_service(None)
        captured = {"value": None}
        handler = service._make_response_handler(captured)
        response = MagicMock()
        response.url = "https://zxfw.court.gov.cn/api/login"
        response.status = 200
        response.headers = {"content-type": "application/json"}
        response.text.return_value = json.dumps({"data": {"token": "captured_token_123"}})
        handler(response)
        assert captured["value"] == "captured_token_123"

    def test_ignores_non_login_url(self):
        service = TestCourtZxfwService._make_service(None)
        captured = {"value": None}
        handler = service._make_response_handler(captured)
        response = MagicMock()
        response.url = "https://zxfw.court.gov.cn/api/other"
        response.status = 200
        handler(response)
        assert captured["value"] is None
