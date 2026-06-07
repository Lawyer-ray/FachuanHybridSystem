"""测试 core.config 子模块

覆盖: config/exceptions.py, config/utils.py, config/cache.py
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.exceptions import (
    ConfigException,
    ConfigFileError,
    ConfigNotFoundError,
    ConfigTypeError,
    ConfigValidationError,
    SensitiveConfigError,
)


# ============================================================
# config/exceptions.py
# ============================================================


class TestConfigExceptions:
    """测试配置管理异常"""

    def test_config_exception(self) -> None:
        exc = ConfigException("something wrong", code="MY_CODE")
        assert exc.message == "something wrong"
        assert exc.code == "MY_CODE"
        assert "MY_CODE" in str(exc)

    def test_config_exception_default_code(self) -> None:
        exc = ConfigException("msg")
        assert exc.code == "ConfigException"

    def test_config_not_found(self) -> None:
        exc = ConfigNotFoundError("missing.key", suggestions=["missing.ke", "missing.key2"])
        assert exc.key == "missing.key"
        assert len(exc.suggestions) == 2
        assert "不存在" in str(exc)
        assert "是否想要" in str(exc)

    def test_config_not_found_no_suggestions(self) -> None:
        exc = ConfigNotFoundError("x")
        assert exc.suggestions == []

    def test_config_type_error(self) -> None:
        exc = ConfigTypeError("port", expected_type=int, actual_type=str, value="abc")
        assert exc.key == "port"
        assert exc.expected_type is int
        assert exc.actual_type is str
        assert "int" in str(exc)
        assert "str" in str(exc)

    def test_config_validation_error(self) -> None:
        exc = ConfigValidationError(errors=["too short", "invalid char"], key="name")
        assert exc.key == "name"
        assert len(exc.errors) == 2

    def test_config_validation_error_no_key(self) -> None:
        exc = ConfigValidationError(errors=["global error"])
        assert exc.key is None
        assert "global error" in str(exc)

    def test_config_file_error(self) -> None:
        original = ValueError("bad yaml")
        exc = ConfigFileError("/etc/config.yaml", line=42, message="parse error", original_error=original)
        assert exc.path == "/etc/config.yaml"
        assert exc.line == 42
        assert exc.original_error is original
        assert "42" in str(exc)

    def test_config_file_error_minimal(self) -> None:
        exc = ConfigFileError("/path/to/config")
        assert "config" in str(exc)

    def test_sensitive_config_error(self) -> None:
        exc = SensitiveConfigError("API_KEY", environment="production")
        assert exc.key == "API_KEY"
        assert exc.environment == "production"
        assert "production" in str(exc)

    def test_sensitive_config_error_no_env(self) -> None:
        exc = SensitiveConfigError("SECRET")
        assert "环境变量" in str(exc)


# ============================================================
# config/utils.py
# ============================================================


class TestConfigUtils:
    """测试配置工具函数"""

    def test_get_config_value_with_fallback(self) -> None:
        from apps.core.config.utils import get_config_value

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False, get_unified_config=None)
        with patch("apps.core.config.utils.settings", mock_settings):
            result = get_config_value("some.key", default="fallback", fallback_settings_key="MY_KEY")
            assert result == "fallback"

    def test_get_config_value_fallback_settings_key(self) -> None:
        from apps.core.config.utils import get_config_value

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False, get_unified_config=None, MY_KEY="from_settings")
        with patch("apps.core.config.utils.settings", mock_settings):
            result = get_config_value("some.key", default="default", fallback_settings_key="MY_KEY")
            assert result == "from_settings"

    def test_get_nested_config_value(self) -> None:
        from apps.core.config.utils import get_nested_config_value

        config = {"key1": "value1", "key2": 42}
        assert get_nested_config_value(config, "key1") == "value1"
        assert get_nested_config_value(config, "key2") == 42
        assert get_nested_config_value(config, "missing", "default") == "default"

    def test_is_config_manager_available(self) -> None:
        from apps.core.config.utils import is_config_manager_available

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=True)
        with patch("apps.core.config.utils.settings", mock_settings):
            assert is_config_manager_available() is True

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False)
        with patch("apps.core.config.utils.settings", mock_settings):
            assert is_config_manager_available() is False

    def test_get_config_manager_none(self) -> None:
        from apps.core.config.utils import get_config_manager

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False)
        with patch("apps.core.config.utils.settings", mock_settings):
            assert get_config_manager() is None

    def test_migrate_legacy_config_access(self) -> None:
        from apps.core.config.utils import migrate_legacy_config_access

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False, OLD_KEY="old_value")
        with patch("apps.core.config.utils.settings", mock_settings):
            result = migrate_legacy_config_access("OLD_KEY", "new.key", "default")
            assert result == "old_value"

    def test_migrate_legacy_config_access_default(self) -> None:
        from apps.core.config.utils import migrate_legacy_config_access

        mock_settings = SimpleNamespace(CONFIG_MANAGER_AVAILABLE=False)
        with patch("apps.core.config.utils.settings", mock_settings):
            result = migrate_legacy_config_access("MISSING", "new.key", "default_val")
            assert result == "default_val"

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_get_system_config_value(self, mock_svc_cls: MagicMock) -> None:
        from apps.core.config.utils import get_system_config_value

        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "config_val"
        mock_svc_cls.return_value = mock_svc
        result = get_system_config_value("my.key", default="d")
        assert result == "config_val"

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("db error"))
    def test_get_system_config_value_fallback(self, mock_svc_cls: MagicMock) -> None:
        from apps.core.config.utils import get_system_config_value

        result = get_system_config_value("my.key", default="fallback")
        assert result == "fallback"


# ============================================================
# infrastructure/cache.py - get_cache_config
# ============================================================


class TestInfrastructureCacheConfig:
    """测试 infrastructure/cache.py 的缓存配置"""

    @patch("apps.core.config.django_runtime.resolve_cache_redis_url")
    @patch("apps.core.infrastructure.cache._safe_get_config", return_value=300)
    def test_get_cache_config_redis(self, mock_safe: MagicMock, mock_resolve: MagicMock) -> None:
        from apps.core.infrastructure.cache import get_cache_config

        mock_resolve.return_value = "redis://localhost:6379/0"
        config = get_cache_config()
        assert "RedisCache" in config["default"]["BACKEND"]
        assert config["default"]["LOCATION"] == "redis://localhost:6379/0"

    @patch("apps.core.config.django_runtime.resolve_cache_redis_url")
    @patch("apps.core.infrastructure.cache._safe_get_config", return_value=300)
    def test_get_cache_config_locmem(self, mock_safe: MagicMock, mock_resolve: MagicMock) -> None:
        from apps.core.infrastructure.cache import get_cache_config

        mock_resolve.return_value = None
        config = get_cache_config()
        assert "LocMemCache" in config["default"]["BACKEND"]
