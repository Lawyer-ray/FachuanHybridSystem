"""Tests for automation/services/scraper/test_service.py — TestService class.

Covers: __init__, organization_service lazy property, test_login success/failure.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestTestServiceInit:
    def test_default_init(self) -> None:
        from apps.automation.services.scraper.test_service import TestService

        svc = TestService()
        assert svc._organization_service is None

    def test_injected_init(self) -> None:
        from apps.automation.services.scraper.test_service import TestService

        mock_os = MagicMock()
        svc = TestService(organization_service=mock_os)
        assert svc._organization_service is mock_os


class TestOrganizationService:
    @patch("apps.core.interfaces.ServiceLocator")
    def test_lazy_loads(self, MockLocator: MagicMock) -> None:
        from apps.automation.services.scraper.test_service import TestService

        svc = TestService()
        MockLocator.get_organization_service.return_value = MagicMock()
        result = svc.organization_service
        assert result is not None
        MockLocator.get_organization_service.assert_called_once()


class TestTestLogin:
    def test_credential_not_found(self) -> None:
        from apps.automation.services.scraper.test_service import TestService

        mock_os = MagicMock()
        mock_os.get_credential.side_effect = Exception("not found")
        svc = TestService(organization_service=mock_os)

        result = svc.test_login(credential_id=999)
        assert result["success"] is False
        assert "登录失败" in result["message"]

    @patch("time.sleep")
    @patch("apps.automation.services.scraper.test_service.ScreenshotUtils")
    @patch("apps.automation.services.scraper.test_service.get_config", return_value=5)
    @patch("apps.core.services.browser.create_browser")
    def test_login_success(
        self,
        mock_browser: MagicMock,
        mock_config: MagicMock,
        mock_screenshot: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        from apps.automation.services.scraper.test_service import TestService

        mock_os = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "user@test.com"
        credential.password = "pass"
        mock_os.get_credential.return_value = credential

        svc = TestService(organization_service=mock_os)

        # Mock browser context manager
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser.return_value.__enter__ = MagicMock(return_value=(mock_page, mock_context))
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)

        # Mock CourtZxfwService
        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as MockCourt:
            mock_court_instance = MagicMock()
            mock_court_instance.login.return_value = {
                "success": True,
                "message": "OK",
                "token": "abc123token",
            }
            MockCourt.return_value = mock_court_instance
            mock_screenshot.collect_screenshots.return_value = ["s1.png"]

            result = svc.test_login(credential_id=1)

            assert result["success"] is True
            assert result["token"] == "abc123token"
            assert len(result["screenshots"]) == 1
            mock_court_instance.login.assert_called_once()

    @patch("time.sleep")
    @patch("apps.automation.services.scraper.test_service.ScreenshotUtils")
    @patch("apps.automation.services.scraper.test_service.get_config", return_value=5)
    @patch("apps.core.services.browser.create_browser")
    def test_login_failure_during_execution(
        self,
        mock_browser: MagicMock,
        mock_config: MagicMock,
        mock_screenshot: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        from apps.automation.services.scraper.test_service import TestService

        mock_os = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "user"
        credential.password = "pass"
        mock_os.get_credential.return_value = credential

        svc = TestService(organization_service=mock_os)

        mock_browser.return_value.__enter__ = MagicMock(return_value=(MagicMock(), MagicMock()))
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as MockCourt:
            MockCourt.return_value.login.side_effect = RuntimeError("Browser crashed")

            result = svc.test_login(credential_id=1)

            assert result["success"] is False
            assert "Browser crashed" in result["message"]
            assert result["error"] is not None

    @patch("time.sleep")
    @patch("apps.automation.services.scraper.test_service.ScreenshotUtils")
    @patch("apps.automation.services.scraper.test_service.get_config", return_value=5)
    @patch("apps.core.services.browser.create_browser")
    def test_login_no_token(
        self,
        mock_browser: MagicMock,
        mock_config: MagicMock,
        mock_screenshot: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        from apps.automation.services.scraper.test_service import TestService

        mock_os = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "user"
        credential.password = "pass"
        mock_os.get_credential.return_value = credential

        svc = TestService(organization_service=mock_os)

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser.return_value.__enter__ = MagicMock(return_value=(mock_page, mock_context))
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService"
        ) as MockCourt:
            mock_court_instance = MagicMock()
            mock_court_instance.login.return_value = {
                "success": True,
                "message": "OK",
                "token": None,
            }
            MockCourt.return_value = mock_court_instance
            mock_screenshot.collect_screenshots.return_value = []

            result = svc.test_login(credential_id=1)

            assert result["success"] is True
            assert result["token"] is None
            assert any("未捕获到 Token" in log for log in result["logs"])
