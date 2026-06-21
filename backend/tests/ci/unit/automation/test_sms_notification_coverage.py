"""Coverage tests for automation services: sms_notification_service, scraper."""

from unittest.mock import MagicMock, patch

import pytest


class TestSMSNotificationService:
    def _make(self):
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService

        case_chat = MagicMock()
        return SMSNotificationService(case_chat_service=case_chat)

    def test_send_no_case(self):
        svc = self._make()
        sms = MagicMock()
        sms.case = None
        sms.id = 1
        result = svc.send_case_chat_notification(sms)
        assert result.any_success is False

    def test_get_available_platforms_error(self):
        svc = self._make()
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_factory:
            mock_factory.get_available_platforms.side_effect = Exception("no factory")
            from apps.core.models.enums import ChatPlatform
            platforms = svc._get_available_platforms()
            assert platforms == [ChatPlatform.FEISHU]

    def test_send_no_platforms(self):
        from apps.core.models.enums import ChatPlatform
        svc = self._make()
        sms = MagicMock()
        sms.case = MagicMock()
        sms.id = 1
        with patch.object(svc, "_get_available_platforms", return_value=[]):
            result = svc.send_case_chat_notification(sms)
            assert result.any_success is False


class TestAutomationManagementCommands:
    def test_bench_http_exists(self):
        from apps.automation.management.commands import bench_http
        assert hasattr(bench_http, "Command")

    def test_clear_token_cache_exists(self):
        from apps.automation.management.commands import clear_token_cache
        assert hasattr(clear_token_cache, "Command")

class TestScraperSecurityServiceConstants:
    def test_gsxt_constants(self):
        from apps.automation.services.gsxt.gsxt_reverse_login import GSXT_BASE, LOGIN_API, CAPTCHA_ID

        assert GSXT_BASE == "https://shiming.gsxt.gov.cn"
        assert "login" in LOGIN_API
        assert len(CAPTCHA_ID) > 0
