"""Comprehensive unit tests for gsxt_login_service."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

_MOD = "apps.automation.services.gsxt.gsxt_login_service"


class TestGsxtLoginError:

    def test_is_exception(self):
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginError

        exc = GsxtLoginError("test")
        assert isinstance(exc, Exception)
        assert str(exc) == "test"


class TestGsxtReportError:

    def test_is_exception(self):
        from apps.automation.services.gsxt.gsxt_login_service import GsxtReportError

        exc = GsxtReportError("report fail")
        assert isinstance(exc, Exception)
        assert str(exc) == "report fail"


class TestWaitCaptchaSuccess:

    @pytest.mark.asyncio
    async def test_success_detected(self):
        from apps.automation.services.gsxt.gsxt_login_service import _wait_captcha_success

        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=True)
        result = await _wait_captcha_success(page, ".geetest_lock_success", timeout=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        from apps.automation.services.gsxt.gsxt_login_service import _wait_captcha_success

        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=False)
        result = await _wait_captcha_success(page, ".geetest_lock_success", timeout=3)
        assert result is False

    @pytest.mark.asyncio
    async def test_page_exception_returns_false(self):
        from apps.automation.services.gsxt.gsxt_login_service import _wait_captcha_success

        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=Exception("page crashed"))
        result = await _wait_captcha_success(page, ".geetest_lock_success", timeout=3)
        assert result is False


class TestClickCompanyDetail:

    @pytest.mark.asyncio
    async def test_company_not_found(self):
        from apps.automation.services.gsxt.gsxt_login_service import (
            GsxtReportError,
            _click_company_detail,
        )

        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        context = MagicMock()
        context.pages = []

        with pytest.raises(GsxtReportError, match="未找到企业"):
            await _click_company_detail(page, "测试公司", context)

    @pytest.mark.asyncio
    async def test_company_found_opens_new_tab(self):
        from apps.automation.services.gsxt.gsxt_login_service import _click_company_detail

        page = AsyncMock()
        # First evaluate returns link info, second returns clicked=True
        page.evaluate = AsyncMock(side_effect=[
            {"href": "http://example.com", "name": "测试公司"},
            True,
        ])
        page.is_closed.return_value = False
        page.url = "http://search.gsxt.gov.cn/result"

        # Use MagicMock (not AsyncMock) since is_closed() is called synchronously
        new_page = MagicMock()
        new_page.is_closed.return_value = False
        new_page.url = "http://detail.gsxt.gov.cn/company"

        context = MagicMock()
        context.pages = []

        captured_cb = {}

        def capture_on(event, callback):
            captured_cb[event] = callback

        context.on = MagicMock(side_effect=capture_on)
        context.remove_listener = MagicMock()

        async def fake_sleep(seconds):
            if "page" in captured_cb:
                await captured_cb["page"](new_page)

        with patch(f"{_MOD}.asyncio.sleep", side_effect=fake_sleep):
            result = await _click_company_detail(page, "测试公司", context)

        assert result is new_page


class TestTryReverseLogin:

    def test_import_error_returns_false(self):
        from apps.automation.services.gsxt.gsxt_login_service import _try_reverse_login

        credential = MagicMock()
        with patch.dict("sys.modules", {"apps.automation.services.gsxt.gsxt_reverse_login": None}):
            result = _try_reverse_login(credential, 1)
            assert result is False

    def test_not_implemented_returns_false(self):
        from apps.automation.services.gsxt.gsxt_login_service import _try_reverse_login

        credential = MagicMock()
        mock_reverse = MagicMock(side_effect=NotImplementedError("not configured"))
        with patch.dict("sys.modules"):
            with patch(f"{_MOD}.reverse_login", mock_reverse, create=True):
                result = _try_reverse_login(credential, 1)
                assert result is False

    def test_exception_returns_false(self):
        from apps.automation.services.gsxt.gsxt_login_service import _try_reverse_login

        credential = MagicMock()
        mock_reverse = MagicMock(side_effect=RuntimeError("failed"))
        with patch(f"{_MOD}.reverse_login", mock_reverse, create=True):
            result = _try_reverse_login(credential, 1)
            assert result is False


class TestStartLoginGsxt:

    @patch(f"{_MOD}._try_reverse_login", return_value=True)
    def test_uses_reverse_login_when_available(self, mock_reverse):
        from apps.automation.services.gsxt.gsxt_login_service import start_login_gsxt

        credential = MagicMock()
        start_login_gsxt(credential, 1)
        mock_reverse.assert_called_once_with(credential, 1)

    @patch(f"{_MOD}.threading.Thread")
    @patch(f"{_MOD}._try_reverse_login", return_value=False)
    def test_fallback_to_chrome(self, mock_reverse, MockThread):
        from apps.automation.services.gsxt.gsxt_login_service import start_login_gsxt

        credential = MagicMock()
        start_login_gsxt(credential, 1)
        mock_reverse.assert_called_once_with(credential, 1)
        MockThread.assert_called_once()
        MockThread.return_value.start.assert_called_once()


class TestRunInThread:

    @patch(f"{_MOD}.asyncio.run")
    def test_runs_full_flow(self, mock_run):
        from apps.automation.services.gsxt.gsxt_login_service import _run_in_thread

        credential = MagicMock()
        _run_in_thread(credential, 42)
        mock_run.assert_called_once()


class TestGsxtLoginServiceFacade:

    @patch(f"{_MOD}.start_login_gsxt")
    def test_start_login(self, mock_start):
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginService

        svc = GsxtLoginService()
        credential = MagicMock()
        svc.start_login(credential, 1)
        mock_start.assert_called_once_with(credential, 1)
