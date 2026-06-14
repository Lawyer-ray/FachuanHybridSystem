"""Tests for apps.core.config.utils."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetConfigValue:
    @patch("apps.core.config.utils.settings")
    def test_fallback_to_default(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = False
        from apps.core.config.utils import get_config_value
        result = get_config_value("some.key", default="fallback")
        assert result == "fallback"

    @patch("apps.core.config.utils.settings")
    def test_fallback_settings_key(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = False
        mock_settings.MY_KEY = "from_settings"
        from apps.core.config.utils import get_config_value
        result = get_config_value("key", fallback_settings_key="MY_KEY")
        assert result == "from_settings"

    @patch("apps.core.config.utils.settings")
    def test_unified_config_available(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = True
        mock_settings.get_unified_config = MagicMock(return_value="unified_val")
        from apps.core.config.utils import get_config_value
        result = get_config_value("some.key")
        assert result == "unified_val"

    @patch("apps.core.config.utils.settings")
    def test_unified_config_returns_none_fallback(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = True
        mock_settings.get_unified_config = MagicMock(return_value=None)
        mock_settings.MY_KEY = "fb"
        from apps.core.config.utils import get_config_value
        result = get_config_value("key", fallback_settings_key="MY_KEY")
        assert result == "fb"

    @patch("apps.core.config.utils.settings")
    def test_unified_config_exception(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = True
        mock_settings.get_unified_config = MagicMock(side_effect=Exception("err"))
        mock_settings.MY_KEY = "fb"
        from apps.core.config.utils import get_config_value
        result = get_config_value("key", fallback_settings_key="MY_KEY")
        assert result == "fb"


class TestGetNestedConfigValue:
    def test_found(self):
        from apps.core.config.utils import get_nested_config_value
        assert get_nested_config_value({"a": 1}, "a") == 1

    def test_not_found(self):
        from apps.core.config.utils import get_nested_config_value
        assert get_nested_config_value({"a": 1}, "b", default="nope") == "nope"


class TestCategoryConfigs:
    """Test category config helpers. SystemConfigService is imported inside functions,
    so we patch at the import path within the function's local scope."""

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_feishu_success(self, mock_svc_cls):
        mock_svc_cls.return_value.get_category_configs.return_value = {"APP_ID": "xxx"}
        from apps.core.config.utils import get_feishu_category_configs
        result = get_feishu_category_configs()
        assert result == {"APP_ID": "xxx"}

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("fail"))
    def test_feishu_failure(self, _):
        from apps.core.config.utils import get_feishu_category_configs
        result = get_feishu_category_configs()
        assert result == {}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_wechat_work_success(self, mock_svc_cls):
        mock_svc_cls.return_value.get_category_configs.return_value = {"CORP_ID": "y"}
        from apps.core.config.utils import get_wechat_work_category_configs
        result = get_wechat_work_category_configs()
        assert "CORP_ID" in result

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("fail"))
    def test_wechat_work_failure(self, _):
        from apps.core.config.utils import get_wechat_work_category_configs
        assert get_wechat_work_category_configs() == {}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_dingtalk_success(self, mock_svc_cls):
        mock_svc_cls.return_value.get_category_configs.return_value = {"APP_KEY": "z"}
        from apps.core.config.utils import get_dingtalk_category_configs
        result = get_dingtalk_category_configs()
        assert "APP_KEY" in result

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("fail"))
    def test_dingtalk_failure(self, _):
        from apps.core.config.utils import get_dingtalk_category_configs
        assert get_dingtalk_category_configs() == {}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_telegram_success(self, mock_svc_cls):
        mock_svc_cls.return_value.get_category_configs.return_value = {"BOT_TOKEN": "t"}
        from apps.core.config.utils import get_telegram_category_configs
        result = get_telegram_category_configs()
        assert "BOT_TOKEN" in result

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("fail"))
    def test_telegram_failure(self, _):
        from apps.core.config.utils import get_telegram_category_configs
        assert get_telegram_category_configs() == {}


class TestGetSystemConfigValue:
    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_success(self, mock_svc_cls):
        mock_svc_cls.return_value.get_value.return_value = "val"
        from apps.core.config.utils import get_system_config_value
        result = get_system_config_value("KEY")
        assert result == "val"

    @patch("apps.core.services.system_config_service.SystemConfigService", side_effect=Exception("fail"))
    def test_failure(self, _):
        from apps.core.config.utils import get_system_config_value
        result = get_system_config_value("KEY", default="d")
        assert result == "d"


class TestConfigManagerUtils:
    @patch("apps.core.config.utils.settings")
    def test_is_config_manager_available(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = True
        from apps.core.config.utils import is_config_manager_available
        assert is_config_manager_available() is True

    @patch("apps.core.config.utils.settings")
    def test_get_config_manager_none(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = False
        from apps.core.config.utils import get_config_manager
        assert get_config_manager() is None

    @patch("apps.core.config.utils.settings")
    def test_get_config_manager_available(self, mock_settings):
        mock_settings.CONFIG_MANAGER_AVAILABLE = True
        mock_manager = MagicMock()
        mock_settings.UNIFIED_CONFIG_MANAGER = mock_manager
        from apps.core.config.utils import get_config_manager
        assert get_config_manager() is mock_manager


class TestRegisterConfigChangeListener:
    @patch("apps.core.config.utils.get_config_manager")
    def test_with_manager(self, mock_get_mgr):
        mock_mgr = MagicMock()
        mock_get_mgr.return_value = mock_mgr
        from apps.core.config.utils import register_config_change_listener
        register_config_change_listener("listener", key_filter="k", prefix_filter="p")
        mock_mgr.add_listener.assert_called_once_with("listener", "k", "p")

    @patch("apps.core.config.utils.get_config_manager", return_value=None)
    def test_without_manager(self, _):
        from apps.core.config.utils import register_config_change_listener
        # Should not raise
        register_config_change_listener("listener")


class TestMigrateLegacyConfigAccess:
    @patch("apps.core.config.utils.is_config_manager_available", return_value=True)
    @patch("apps.core.config.utils.settings")
    def test_unified_available(self, mock_settings, _):
        mock_settings.get_unified_config = MagicMock(return_value="unified")
        from apps.core.config.utils import migrate_legacy_config_access
        result = migrate_legacy_config_access("LEGACY_KEY", "unified.key")
        assert result == "unified"

    @patch("apps.core.config.utils.is_config_manager_available", return_value=False)
    @patch("apps.core.config.utils.settings")
    def test_fallback_to_legacy(self, mock_settings, _):
        mock_settings.LEGACY_KEY = "legacy_val"
        from apps.core.config.utils import migrate_legacy_config_access
        result = migrate_legacy_config_access("LEGACY_KEY", "unified.key", default="def")
        assert result == "legacy_val"

    @patch("apps.core.config.utils.is_config_manager_available", return_value=True)
    @patch("apps.core.config.utils.settings")
    def test_unified_returns_none_fallback(self, mock_settings, _):
        mock_settings.get_unified_config = MagicMock(return_value=None)
        mock_settings.LEGACY_KEY = "from_legacy"
        from apps.core.config.utils import migrate_legacy_config_access
        result = migrate_legacy_config_access("LEGACY_KEY", "unified.key")
        assert result == "from_legacy"

    @patch("apps.core.config.utils.is_config_manager_available", return_value=True)
    @patch("apps.core.config.utils.settings")
    def test_unified_exception_fallback(self, mock_settings, _):
        mock_settings.get_unified_config = MagicMock(side_effect=Exception("err"))
        mock_settings.LEGACY_KEY = "legacy_val"
        from apps.core.config.utils import migrate_legacy_config_access
        result = migrate_legacy_config_access("LEGACY_KEY", "unified.key")
        assert result == "legacy_val"
