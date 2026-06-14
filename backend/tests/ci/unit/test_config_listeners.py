"""Tests for apps.core.config.listeners — ConfigChangeLogger, ConfigValidationListener, ConfigSecurityListener."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.listeners import (
    ConfigChangeLogger,
    ConfigSecurityListener,
    ConfigValidationListener,
)


class TestConfigChangeLogger:
    def test_on_config_changed_normal(self):
        logger = ConfigChangeLogger()
        # Should not raise
        logger.on_config_changed("db.host", "old", "new")

    def test_on_config_changed_sensitive(self):
        logger = ConfigChangeLogger()
        logger.on_config_changed("password", "secret123", "newsecret")

    def test_on_config_added(self):
        logger = ConfigChangeLogger()
        logger.on_config_added("new.key", "value")

    def test_on_config_added_sensitive(self):
        logger = ConfigChangeLogger()
        logger.on_config_added("api_key", "sk-1234567890")

    def test_on_config_removed(self):
        logger = ConfigChangeLogger()
        logger.on_config_removed("old.key", "value")

    def test_on_config_removed_sensitive(self):
        logger = ConfigChangeLogger()
        logger.on_config_removed("token", "abc123")

    def test_on_config_reloaded(self):
        logger = ConfigChangeLogger()
        logger.on_config_reloaded()

    def test_mask_value_none(self):
        logger = ConfigChangeLogger()
        assert logger._mask_value(None) == "None"

    def test_mask_value_short(self):
        logger = ConfigChangeLogger()
        assert logger._mask_value("abc") == "***"

    def test_mask_value_medium(self):
        logger = ConfigChangeLogger()
        result = logger._mask_value("abcdef")
        assert "***" in result

    def test_mask_value_long(self):
        logger = ConfigChangeLogger()
        result = logger._mask_value("abcdefghijklmnop")
        assert "***" in result
        assert result.startswith("abc")

    def test_is_sensitive_key(self):
        logger = ConfigChangeLogger()
        assert logger._is_sensitive_key("password") is True
        assert logger._is_sensitive_key("secret_key") is True
        assert logger._is_sensitive_key("token") is True
        assert logger._is_sensitive_key("db.host") is False


class TestConfigValidationListener:
    def test_valid_debug(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("django.debug", False, True)

    def test_invalid_debug_type(self):
        listener = ConfigValidationListener()
        # Should log error, not raise
        listener.on_config_changed("django.debug", False, "yes")

    def test_valid_secret_key(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("django.secret_key", "old", "a" * 30)

    def test_invalid_secret_key_short(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("django.secret_key", "old", "short")

    def test_valid_timeout(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("redis.timeout", 5, 10)

    def test_invalid_timeout(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("redis.timeout", 5, -1)

    def test_valid_max_retries(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("http.max_retries", 0, 3)

    def test_invalid_max_retries(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("http.max_retries", 0, -1)

    def test_valid_port(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("server.port", 8000, 8080)

    def test_invalid_port(self):
        listener = ConfigValidationListener()
        listener.on_config_changed("server.port", 8000, 99999)

    def test_on_config_added(self):
        listener = ConfigValidationListener()
        listener.on_config_added("new.timeout", 5)


class TestConfigSecurityListener:
    def test_non_critical_key(self):
        listener = ConfigSecurityListener()
        listener.on_config_changed("db.host", "old", "new")

    def test_critical_key_secret(self):
        listener = ConfigSecurityListener()
        with patch("django.conf.settings") as mock_s:
            mock_s.DEBUG = True
            listener.on_config_changed("django.secret_key", "old", "new")

    def test_critical_key_password(self):
        listener = ConfigSecurityListener()
        with patch("django.conf.settings") as mock_s:
            mock_s.DEBUG = True
            listener.on_config_changed("database.password", "old", "new")

    def test_on_config_added_critical(self):
        listener = ConfigSecurityListener()
        with patch("django.conf.settings") as mock_s:
            mock_s.DEBUG = True
            listener.on_config_added("secret.config", "value")

    def test_on_config_removed_critical(self):
        listener = ConfigSecurityListener()
        with patch("django.conf.settings") as mock_s:
            mock_s.DEBUG = True
            listener.on_config_removed("password.config", "old")

    def test_production_debug_false(self):
        listener = ConfigSecurityListener()
        with patch("django.conf.settings") as mock_s:
            mock_s.DEBUG = False
            listener.on_config_changed("django.secret_key", "old", "new")

    def test_is_security_critical(self):
        listener = ConfigSecurityListener()
        assert listener._is_security_critical("django.secret_key") is True
        assert listener._is_security_critical("database.password") is True
        assert listener._is_security_critical("permissions.open_access") is True
        assert listener._is_security_critical("my_secret_key") is True
        assert listener._is_security_critical("db.host") is False
