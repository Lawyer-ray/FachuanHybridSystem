"""core/config/utils.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.utils import (
    get_case_chat_config,
    get_config_manager,
    get_config_value,
    get_court_sms_config,
    get_document_processing_config,
    get_dingtalk_category_configs,
    get_feishu_category_configs,
    get_feishu_config,
    get_nested_config_value,
    get_system_config_value,
    get_telegram_category_configs,
    get_wechat_work_category_configs,
    is_config_manager_available,
    migrate_legacy_config_access,
    register_config_change_listener,
)


class TestGetConfigValue:
    def test_returns_default_when_no_manager(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            result = get_config_value("key", default="fallback")
            assert result == "fallback"

    def test_returns_unified_config_value(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="unified_val")
            result = get_config_value("key", default="fallback")
            assert result == "unified_val"

    def test_falls_back_to_django_settings(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.MY_KEY = "django_val"
            result = get_config_value("key", default="fallback", fallback_settings_key="MY_KEY")
            assert result == "django_val"

    def test_returns_default_on_exception(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(side_effect=Exception("boom"))
            result = get_config_value("key", default="safe")
            assert result == "safe"


class TestGetNestedConfigValue:
    def test_returns_value(self) -> None:
        assert get_nested_config_value({"a": 1}, "a") == 1

    def test_returns_default(self) -> None:
        assert get_nested_config_value({"a": 1}, "b", "x") == "x"


class TestCategoryConfigs:
    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_feishu_configs(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_category_configs.return_value = {"k": "v"}
        result = get_feishu_category_configs()
        assert result == {"k": "v"}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_feishu_configs_exception(self, mock_cls: MagicMock) -> None:
        mock_cls.side_effect = Exception("db error")
        result = get_feishu_category_configs()
        assert result == {}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_wechat_work_configs(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_category_configs.return_value = {"k": "v"}
        result = get_wechat_work_category_configs()
        assert result == {"k": "v"}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_dingtalk_configs(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_category_configs.return_value = {"k": "v"}
        result = get_dingtalk_category_configs()
        assert result == {"k": "v"}

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_telegram_configs(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_category_configs.return_value = {"k": "v"}
        result = get_telegram_category_configs()
        assert result == {"k": "v"}


class TestGetSystemConfigValue:
    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_returns_value(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_value.return_value = "val"
        assert get_system_config_value("k") == "val"

    @patch("apps.core.services.system_config_service.SystemConfigService")
    def test_returns_default_on_exception(self, mock_cls: MagicMock) -> None:
        mock_cls.side_effect = Exception("boom")
        assert get_system_config_value("k", "d") == "d"


class TestGetFeishuConfig:
    def test_returns_from_unified(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="uv")
            mock_settings.FEISHU = {}
            mock_settings.COURT_SMS_PROCESSING = {}
            assert get_feishu_config("app_id") == "uv"

    def test_returns_from_feishu_dict(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {"APP_ID": "fid"}
            mock_settings.COURT_SMS_PROCESSING = {}
            assert get_feishu_config("app_id") == "fid"

    def test_returns_from_legacy(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {}
            mock_settings.COURT_SMS_PROCESSING = {"FEISHU_APP_ID": "legacy"}
            assert get_feishu_config("app_id") == "legacy"

    def test_returns_default(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {}
            mock_settings.COURT_SMS_PROCESSING = {}
            assert get_feishu_config("app_id", "def") == "def"


class TestDocumentProcessingConfig:
    def test_returns_unified(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="uv")
            mock_settings.DOCUMENT_PROCESSING = {}
            assert get_document_processing_config("key") == "uv"

    def test_returns_legacy(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.DOCUMENT_PROCESSING = {"KEY": "leg"}
            assert get_document_processing_config("key") == "leg"


class TestCaseChatConfig:
    def test_returns_unified(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="uv")
            mock_settings.CASE_CHAT = {}
            assert get_case_chat_config("key") == "uv"

    def test_returns_legacy(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.CASE_CHAT = {"KEY": "leg"}
            assert get_case_chat_config("key") == "leg"


class TestCourtSmsConfig:
    def test_returns_unified(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="uv")
            mock_settings.COURT_SMS_PROCESSING = {}
            assert get_court_sms_config("key") == "uv"

    def test_returns_legacy(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.COURT_SMS_PROCESSING = {"KEY": "leg"}
            assert get_court_sms_config("key") == "leg"


class TestConfigManagerFunctions:
    def test_is_config_manager_available_true(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            assert is_config_manager_available() is True

    def test_is_config_manager_available_false(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            assert is_config_manager_available() is False

    def test_get_config_manager_when_available(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.UNIFIED_CONFIG_MANAGER = "mgr"
            assert get_config_manager() == "mgr"

    def test_get_config_manager_when_unavailable(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            assert get_config_manager() is None

    def test_register_config_change_listener(self) -> None:
        with patch("apps.core.config.utils.get_config_manager", return_value=MagicMock()):
            register_config_change_listener("listener", key_filter="k")

    def test_register_listener_no_manager(self) -> None:
        with patch("apps.core.config.utils.get_config_manager", return_value=None):
            register_config_change_listener("listener")  # should not raise


class TestMigrateLegacyConfigAccess:
    def test_returns_unified(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = MagicMock(return_value="uv")
            assert migrate_legacy_config_access("OLD_KEY", "new.key") == "uv"

    def test_returns_legacy(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.OLD_KEY = "leg"
            assert migrate_legacy_config_access("OLD_KEY", "new.key") == "leg"

    def test_returns_default(self) -> None:
        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            del mock_settings.OLD_KEY  # ensure attribute doesn't exist
            assert migrate_legacy_config_access("OLD_KEY", "new.key", "def") == "def"
