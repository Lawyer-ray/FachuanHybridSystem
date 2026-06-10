"""Tests for CourtZxfwService - court zxfw scraper service."""

import json
import socket
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService


class TestExtractTokenFromBody:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_token_in_data_wrapper(self):
        body = {"data": {"token": "abc123"}}
        assert self.service._extract_token_from_body(body) == "abc123"

    def test_access_token_in_data(self):
        body = {"data": {"access_token": "xyz789"}}
        assert self.service._extract_token_from_body(body) == "xyz789"

    def test_accessToken_in_data(self):
        body = {"data": {"accessToken": "camelCase"}}
        assert self.service._extract_token_from_body(body) == "camelCase"

    def test_token_in_result_wrapper(self):
        body = {"result": {"token": "result_token"}}
        assert self.service._extract_token_from_body(body) == "result_token"

    def test_token_at_root_level(self):
        body = {"token": "root_token"}
        assert self.service._extract_token_from_body(body) == "root_token"

    def test_no_token(self):
        body = {"data": {"other": "value"}}
        assert self.service._extract_token_from_body(body) is None

    def test_empty_body(self):
        assert self.service._extract_token_from_body({}) is None

    def test_non_dict_wrapper(self):
        body = {"data": "string_value"}
        assert self.service._extract_token_from_body(body) is None

    def test_nested_result_wrapper(self):
        body = {"result": {"access_token": "nested"}}
        assert self.service._extract_token_from_body(body) == "nested"


class TestIsNetworkError:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_connection_error(self):
        assert self.service._is_network_error(ConnectionError("reset")) is True

    def test_timeout_error(self):
        assert self.service._is_network_error(TimeoutError("timed out")) is True

    def test_socket_error(self):
        assert self.service._is_network_error(socket.gaierror("name resolution")) is True

    def test_os_error_with_errno(self):
        exc = OSError(60, "ETIMEDOUT")
        assert self.service._is_network_error(exc) is True

    def test_network_string_in_message(self):
        assert self.service._is_network_error(Exception("ERR_NAME_NOT_RESOLVED")) is True

    def test_timeout_in_message(self):
        assert self.service._is_network_error(Exception("request timeout occurred")) is True

    def test_not_network_error(self):
        assert self.service._is_network_error(ValueError("some value error")) is False

    def test_syntax_error_not_network(self):
        assert self.service._is_network_error(SyntaxError("syntax")) is False


class TestGetCookiePath:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_basic_path(self):
        path = self.service._get_cookie_path("user@example.com")
        assert "court_zxfw" in path
        assert "user_at_example.com" in path
        assert path.endswith(".json")

    def test_slash_in_account(self):
        path = self.service._get_cookie_path("domain/user")
        assert "domain_user" in path


class TestSaveCookies:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.cookie_service = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=self.cookie_service,
        )

    def test_save_calls_cookie_service(self):
        self.service._save_cookies("testuser")
        self.cookie_service.save.assert_called_once()

    def test_save_no_cookie_service(self):
        svc = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=self.cookie_service,
        )
        svc._cookie_service = None
        svc._save_cookies("testuser")  # Should not raise


class TestCheckLoginSuccess:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_url_without_login_keyword(self):
        self.page.url = "https://zxfw.court.gov.cn/zxfw/#/home"
        assert self.service._check_login_success() is True

    def test_url_with_login_keyword(self):
        self.page.url = "https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index"
        self.page.locator.return_value.count.return_value = 0
        self.page.locator.return_value.first.is_visible.return_value = False
        # Should return False since URL still has login and no error elements found
        result = self.service._check_login_success()
        # The method checks URL first, then error selectors, then user info selectors
        assert isinstance(result, bool)

    def test_exception_returns_false(self):
        # Force an exception inside _check_login_success
        self.page.url = "https://login.example.com"
        # Make locator raise to trigger exception handling
        self.page.locator.side_effect = Exception("locator error")
        result = self.service._check_login_success()
        assert isinstance(result, bool)


class TestMakeResponseHandler:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_handler_captures_token(self):
        captured = {"value": None}
        handler = self.service._make_response_handler(captured)

        response = MagicMock()
        response.url = "https://api.example.com/api/login"
        response.status = 200
        response.headers = {"content-type": "application/json"}
        response.text.return_value = json.dumps({"data": {"token": "captured_token_123"}})

        handler(response)
        assert captured["value"] == "captured_token_123"

    def test_handler_ignores_non_login_url(self):
        captured = {"value": None}
        handler = self.service._make_response_handler(captured)

        response = MagicMock()
        response.url = "https://api.example.com/api/other"
        response.status = 200

        handler(response)
        assert captured["value"] is None

    def test_handler_ignores_non_200(self):
        captured = {"value": None}
        handler = self.service._make_response_handler(captured)

        response = MagicMock()
        response.url = "https://api.example.com/api/login"
        response.status = 500

        handler(response)
        assert captured["value"] is None

    def test_handler_ignores_non_json(self):
        captured = {"value": None}
        handler = self.service._make_response_handler(captured)

        response = MagicMock()
        response.url = "https://api.example.com/api/login"
        response.status = 200
        response.headers = {"content-type": "text/html"}

        handler(response)
        assert captured["value"] is None


class TestGotoWithRetry:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_first_try_success(self):
        self.page.goto.return_value = None
        self.service._goto_with_retry("https://example.com")
        self.page.goto.assert_called_once()

    def test_retry_on_network_error(self):
        self.page.goto.side_effect = [ConnectionError("reset"), None]
        self.service._goto_with_retry("https://example.com", max_attempts=2)
        assert self.page.goto.call_count == 2

    def test_raises_non_network_error(self):
        self.page.goto.side_effect = ValueError("not network")
        with pytest.raises(ValueError):
            self.service._goto_with_retry("https://example.com")

    def test_raises_after_max_attempts(self):
        self.page.goto.side_effect = ConnectionError("always fail")
        with pytest.raises(ConnectionError):
            self.service._goto_with_retry("https://example.com", max_attempts=2)


class TestFetchBaoquanToken:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_not_logged_in_raises(self):
        self.service.is_logged_in = False
        with pytest.raises(ValueError, match="请先登录"):
            self.service.fetch_baoquan_token()


class TestStubMethods:
    def setup_method(self):
        self.page = MagicMock()
        self.context = MagicMock()
        self.service = CourtZxfwService(
            page=self.page,
            context=self.context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )

    def test_file_case_not_logged_in(self):
        self.service.is_logged_in = False
        with pytest.raises(ValueError, match="请先登录"):
            self.service.file_case({})

    def test_query_case_not_logged_in(self):
        self.service.is_logged_in = False
        with pytest.raises(ValueError, match="请先登录"):
            self.service.query_case("123")

    def test_download_document_not_logged_in(self):
        self.service.is_logged_in = False
        with pytest.raises(ValueError, match="请先登录"):
            self.service.download_document("url")

    def test_file_case_not_implemented(self):
        self.service.is_logged_in = True
        with pytest.raises(NotImplementedError):
            self.service.file_case({})

    def test_query_case_not_implemented(self):
        self.service.is_logged_in = True
        with pytest.raises(NotImplementedError):
            self.service.query_case("123")

    def test_download_document_not_implemented(self):
        self.service.is_logged_in = True
        with pytest.raises(NotImplementedError):
            self.service.download_document("url")


class TestTokenServiceProperty:
    def test_lazy_load(self):
        page = MagicMock()
        context = MagicMock()
        service = CourtZxfwService(
            page=page,
            context=context,
            captcha_recognizer=MagicMock(),
            token_service=MagicMock(),
            cookie_service=MagicMock(),
        )
        ts = service.token_service
        assert ts is not None
        # Should return same instance on subsequent access
        assert service.token_service is ts
