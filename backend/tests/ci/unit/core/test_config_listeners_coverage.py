"""Coverage tests for core.config.listeners."""

from unittest.mock import MagicMock, patch

import pytest


class TestConfigChangeLogger:
    def _make(self):
        from apps.core.config.listeners import ConfigChangeLogger

        return ConfigChangeLogger()

    def test_on_config_changed_normal(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("app.name", "old", "new")
            mock_log.info.assert_called_once()

    def test_on_config_changed_sensitive(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("database.password", "secret123", "newsecret456")
            mock_log.info.assert_called_once()

    def test_on_config_added(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_added("api_key", "sk-12345678")
            mock_log.info.assert_called_once()

    def test_on_config_removed(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_removed("secret_token", "old_value_here")
            mock_log.info.assert_called_once()

    def test_on_config_reloaded(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_reloaded()
            mock_log.info.assert_called_once()

    def test_is_sensitive_key_true(self):
        obj = self._make()
        assert obj._is_sensitive_key("database.password") is True
        assert obj._is_sensitive_key("API_TOKEN") is True
        assert obj._is_sensitive_key("secret_key") is True

    def test_is_sensitive_key_false(self):
        obj = self._make()
        assert obj._is_sensitive_key("app.name") is False
        assert obj._is_sensitive_key("debug_mode") is False

    def test_mask_value_none(self):
        obj = self._make()
        assert obj._mask_value(None) == "None"

    def test_mask_value_short(self):
        obj = self._make()
        assert obj._mask_value("ab") == "***"

    def test_mask_value_medium(self):
        obj = self._make()
        result = obj._mask_value("abcdef")
        assert result.startswith("ab")
        assert "***" in result

    def test_mask_value_long(self):
        obj = self._make()
        result = obj._mask_value("verylongvalue")
        assert result.startswith("ver")
        assert "***" in result


class TestConfigValidationListener:
    def _make(self):
        from apps.core.config.listeners import ConfigValidationListener

        return ConfigValidationListener()

    def test_on_config_changed_debug_bool(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger"):
            obj.on_config_changed("django.debug", None, True)

    def test_on_config_changed_debug_invalid(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("django.debug", None, "yes")
            mock_log.error.assert_called_once()

    def test_on_config_changed_secret_key_short(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("django.secret_key", None, "short")
            mock_log.error.assert_called_once()

    def test_on_config_changed_timeout_positive(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger"):
            obj.on_config_changed("request.timeout", 10, 30)

    def test_on_config_changed_timeout_negative(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("request.timeout", 10, -5)
            mock_log.error.assert_called_once()

    def test_on_config_changed_port_valid(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger"):
            obj.on_config_changed("server.port", 8080, 9090)

    def test_on_config_changed_port_invalid(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger") as mock_log:
            obj.on_config_changed("server.port", 8080, 99999)
            mock_log.error.assert_called_once()

    def test_on_config_added(self):
        obj = self._make()
        with patch("apps.core.config.listeners.logger"):
            obj.on_config_added("app.timeout", 30)


class TestConfigSecurityListener:
    def _make(self):
        from apps.core.config.listeners import ConfigSecurityListener

        return ConfigSecurityListener()

    @patch("apps.core.config.listeners.logger")
    def test_on_config_changed_security_critical(self, mock_log):
        obj = self._make()
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = True
            obj.on_config_changed("django.secret_key", "old", "new")
            mock_log.warning.assert_called_once()

    @patch("apps.core.config.listeners.logger")
    def test_on_config_changed_not_critical(self, mock_log):
        obj = self._make()
        obj.on_config_changed("app.name", "old", "new")
        mock_log.warning.assert_not_called()

    @patch("apps.core.config.listeners.logger")
    def test_on_config_added_security(self, mock_log):
        obj = self._make()
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = True
            obj.on_config_added("database.password", "pass")
            mock_log.warning.assert_called_once()

    @patch("apps.core.config.listeners.logger")
    def test_on_config_removed_security(self, mock_log):
        obj = self._make()
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = True
            obj.on_config_removed("database.password", "old_pass")
            mock_log.error.assert_called_once()

    def test_is_security_critical_true(self):
        obj = self._make()
        assert obj._is_security_critical("django.secret_key") is True
        assert obj._is_security_critical("my_secret_value") is True
        assert obj._is_security_critical("user_password") is True

    def test_is_security_critical_false(self):
        obj = self._make()
        assert obj._is_security_critical("app.name") is False
