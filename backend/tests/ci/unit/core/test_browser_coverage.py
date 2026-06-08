"""Coverage tests for core.services.browser profiles, service, launcher, chrome_process, cdp_connector."""

from unittest.mock import MagicMock, patch

import pytest


class TestBrowserProfile:
    def test_defaults(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test")
        assert p.name == "test"
        assert p.browser_type == "chromium"
        assert p.headless is True
        assert p.anti_detection is True

    def test_properties(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test", cdp_url="http://localhost:9222")
        assert p.is_cdp is True
        assert p.is_remote is False

    def test_is_remote(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test", remote_url="http://remote")
        assert p.is_remote is True

    def test_is_persistent(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test", user_data_dir="/data")
        assert p.is_persistent is True

    def test_to_launch_args(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test", headless=False, slow_mo=100, proxy="http://proxy")
        args = p.to_launch_args()
        assert args["headless"] is False
        assert args["slow_mo"] == 100

    def test_to_context_args(self):
        from apps.core.services.browser.profiles import BrowserProfile

        p = BrowserProfile(name="test", user_agent="Mozilla/5.0")
        args = p.to_context_args()
        assert args["user_agent"] == "Mozilla/5.0"
        assert "viewport" in args

    def test_from_env(self):
        import os
        from apps.core.services.browser.profiles import BrowserProfile

        with patch.dict(os.environ, {"BROWSER_TEST_HEADLESS": "false"}):
            p = BrowserProfile.from_env("test")
            assert p.headless is False

    def test_get_profile_default(self):
        from apps.core.services.browser.profiles import get_profile

        with patch("apps.core.services.browser.profiles._apply_headless_override", side_effect=lambda p: p):
            p = get_profile("default")
            assert p.name == "default"

    def test_get_profile_unknown(self):
        from apps.core.services.browser.profiles import get_profile

        with patch("apps.core.services.browser.profiles._apply_headless_override", side_effect=lambda p: p):
            p = get_profile("nonexistent_profile_xyz")
            assert p.name == "default"

    def test_register_profile(self):
        from apps.core.services.browser.profiles import BrowserProfile, register_profile, get_profile

        custom = BrowserProfile(name="custom_test_xyz")
        register_profile(custom)
        with patch("apps.core.services.browser.profiles._apply_headless_override", side_effect=lambda p: p):
            p = get_profile("custom_test_xyz")
            assert p.name == "custom_test_xyz"


class TestChromeProcess:
    def test_detect_chrome_path(self):
        from apps.core.services.browser.chrome_process import _detect_chrome_path

        path = _detect_chrome_path()
        assert isinstance(path, str)
        assert len(path) > 0

    @patch("apps.core.services.browser.chrome_process.httpx")
    def test_is_cdp_ready_false(self, mock_httpx):
        from apps.core.services.browser.chrome_process import is_cdp_ready

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client
        mock_httpx.HTTPTransport.return_value = MagicMock()
        assert is_cdp_ready() is False


class TestCleanup:
    def test_cleanup_none_objects(self):
        from apps.core.services.browser.launcher import _cleanup

        # Should not raise
        _cleanup(None, None, None)

    def test_cleanup_with_mock_objects(self):
        from apps.core.services.browser.launcher import _cleanup

        page = MagicMock()
        context = MagicMock()
        browser = MagicMock()
        _cleanup(page, context, browser)
        page.close.assert_called_once()
        context.close.assert_called_once()
        browser.close.assert_called_once()

    def test_cleanup_with_error(self):
        from apps.core.services.browser.launcher import _cleanup

        page = MagicMock()
        page.close.side_effect = Exception("fail")
        _cleanup(page, None, None)
        # Should not raise
