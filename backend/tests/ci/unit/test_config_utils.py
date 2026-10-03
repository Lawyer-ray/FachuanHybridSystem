"""Tests for apps.core.config.utils."""

from __future__ import annotations

from unittest.mock import patch


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
