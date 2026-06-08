"""Comprehensive unit tests for gsxt_login_service."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

_MOD = "apps.automation.services.gsxt.gsxt_login_service"


class TestModuleConstants:

    def test_constants_defined(self):
        from apps.automation.services.gsxt.gsxt_login_service import (
            GSXT_LOGIN_URL,
            GSXT_SEARCH_URL,
            CDP_URL,
            CHROME_PATH,
            CHROME_USER_DATA_DIR,
            LOGIN_CAPTCHA_TIMEOUT,
            REPORT_CAPTCHA_TIMEOUT,
        )

        assert "gsxt.gov.cn" in GSXT_LOGIN_URL
        assert "gsxt.gov.cn" in GSXT_SEARCH_URL
        assert CDP_URL.startswith("http://")
        assert CHROME_PATH
        assert CHROME_USER_DATA_DIR
        assert LOGIN_CAPTCHA_TIMEOUT > 0
        assert REPORT_CAPTCHA_TIMEOUT > 0


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


class TestKillExistingChrome:

    @patch(f"{_MOD}.subprocess.run")
    def test_pgrep_finds_process(self, mock_run):
        from apps.automation.services.gsxt.gsxt_login_service import _kill_existing_chrome

        # pgrep returns output (process found)
        mock_run.side_effect = [
            MagicMock(stdout="12345 chrome\n", returncode=0),
            MagicMock(returncode=0),
        ]
        _kill_existing_chrome()
        assert mock_run.call_count == 2

    @patch(f"{_MOD}.subprocess.run")
    def test_no_process_found(self, mock_run):
        from apps.automation.services.gsxt.gsxt_login_service import _kill_existing_chrome

        mock_run.return_value = MagicMock(stdout="", returncode=1)
        _kill_existing_chrome()
        # Only pgrep called, no pkill
        assert mock_run.call_count == 1

    @patch(f"{_MOD}.subprocess.run")
    def test_exception_swallowed(self, mock_run):
        from apps.automation.services.gsxt.gsxt_login_service import _kill_existing_chrome

        mock_run.side_effect = OSError("not found")
        _kill_existing_chrome()  # should not raise


class TestEnsureChromeRunning:

    @patch("apps.core.services.browser.chrome_process.is_cdp_ready", return_value=True)
    def test_already_running(self, mock_cdp):
        from apps.automation.services.gsxt.gsxt_login_service import _ensure_chrome_running

        _ensure_chrome_running()
        mock_cdp.assert_called_once_with(9222)

    @patch("apps.core.services.browser.chrome_process.launch_chrome")
    @patch(f"{_MOD}._kill_existing_chrome")
    @patch("apps.core.services.browser.chrome_process.is_cdp_ready", return_value=False)
    def test_launches_chrome(self, mock_cdp, mock_kill, mock_launch):
        from apps.automation.services.gsxt.gsxt_login_service import _ensure_chrome_running

        _ensure_chrome_running()
        mock_kill.assert_called_once()
        mock_launch.assert_called_once()

    @patch("apps.core.services.browser.chrome_process.launch_chrome", side_effect=RuntimeError("cannot start"))
    @patch(f"{_MOD}._kill_existing_chrome")
    @patch("apps.core.services.browser.chrome_process.is_cdp_ready", return_value=False)
    def test_launch_failure_raises_login_error(self, mock_cdp, mock_kill, mock_launch):
        from apps.automation.services.gsxt.gsxt_login_service import (
            GsxtLoginError,
            _ensure_chrome_running,
        )

        with pytest.raises(GsxtLoginError):
            _ensure_chrome_running()


class TestCdpNavigate:

    @pytest.mark.asyncio
    async def test_no_tabs_raises(self):
        from apps.automation.services.gsxt.gsxt_login_service import (
            GsxtLoginError,
            _cdp_navigate,
        )

        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = []
        with patch(f"{_MOD}.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(GsxtLoginError, match="CDP 无可用页面"):
                await _cdp_navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_navigates_to_url(self):
        from apps.automation.services.gsxt.gsxt_login_service import _cdp_navigate

        tab = {"type": "page", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/1"}
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = [tab]

        recv_messages = [
            '{"id":1,"result":{}}',
            '{"id":2,"result":{}}',
            '{"id":3,"result":{"result":{"value":"https://shiming.gsxt.gov.cn/login"}}}',
        ]
        recv_iter = iter(recv_messages)

        mock_ws = MagicMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=lambda: next(recv_iter))

        # Build a proper async context manager mock for websockets.connect
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            with patch("websockets.connect", return_value=mock_cm):
                result = await _cdp_navigate("https://shiming.gsxt.gov.cn/login", wait_seconds=0)
                assert "gsxt.gov.cn" in result


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
    @patch(f"{_MOD}._ensure_chrome_running")
    @patch(f"{_MOD}._try_reverse_login", return_value=False)
    def test_fallback_to_chrome(self, mock_reverse, mock_chrome, MockThread):
        from apps.automation.services.gsxt.gsxt_login_service import start_login_gsxt

        credential = MagicMock()
        start_login_gsxt(credential, 1)
        mock_chrome.assert_called_once()
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
