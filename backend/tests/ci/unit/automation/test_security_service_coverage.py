"""Coverage tests for automation.services.scraper.core.security_service."""

from unittest.mock import MagicMock, patch

import pytest


class TestSecurityService:
    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_init_with_generated_key(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        assert svc.cipher is not None

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_encrypt_decrypt(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        encrypted = svc.encrypt("hello world")
        assert encrypted != "hello world"
        decrypted = svc.decrypt(encrypted)
        assert decrypted == "hello world"

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_encrypt_empty(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        assert svc.encrypt("") == ""

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_decrypt_empty(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        assert svc.decrypt("") == ""

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_mask_sensitive_data(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        data = {"name": "test", "password": "secret123", "token": "tk"}
        masked = svc.mask_sensitive_data(data)
        assert masked["name"] == "test"
        assert masked["password"] != "secret123"

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_encrypt_decrypt_config(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService

        svc = SecurityService()
        config = {"host": "localhost", "password": "mysecret"}
        encrypted = svc.encrypt_config(config)
        assert encrypted["password_encrypted"] is True
        decrypted = svc.decrypt_config(encrypted)
        assert decrypted["password"] == "mysecret"
        assert "password_encrypted" not in decrypted


class TestSecurityServiceAdapter:
    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_adapter_encrypt(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService, SecurityServiceAdapter

        svc = SecurityService()
        adapter = SecurityServiceAdapter(service=svc)
        encrypted = adapter.encrypt("test")
        assert adapter.decrypt(encrypted) == "test"

    @patch("apps.automation.services.scraper.core.security_service.get_config", return_value=None)
    @patch("django.conf.settings")
    def test_adapter_mask(self, mock_settings, mock_config):
        mock_settings.DEBUG = True
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        from apps.automation.services.scraper.core.security_service import SecurityService, SecurityServiceAdapter

        svc = SecurityService()
        adapter = SecurityServiceAdapter(service=svc)
        result = adapter.mask_sensitive_data({"password": "secret"})
        assert result["password"] != "secret"
