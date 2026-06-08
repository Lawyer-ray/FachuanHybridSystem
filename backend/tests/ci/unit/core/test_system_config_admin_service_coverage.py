"""apps/core/services/system_config_admin_service.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.system_config_admin_service import SystemConfigAdminService


class TestGetDefaultConfigs:
    """测试 SystemConfigAdminService.get_default_configs"""

    def setup_method(self) -> None:
        self.svc = SystemConfigAdminService()

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_returns_list(self, mock_get: MagicMock) -> None:
        """返回值是列表且保持原长度。"""
        mock_get.return_value = [
            {"key": "FOO", "value": "bar", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert isinstance(result, list)
        assert len(result) == 1

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_secret_value_cleared(self, mock_get: MagicMock) -> None:
        """is_secret=True 的配置项 value 应被清空。"""
        mock_get.return_value = [
            {"key": "MY_SECRET", "value": "s3cret!", "is_secret": True},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == ""

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_api_key_suffix_cleared(self, mock_get: MagicMock) -> None:
        """key 以 API_KEY 结尾的配置项 value 应被清空。"""
        mock_get.return_value = [
            {"key": "OPENAI_API_KEY", "value": "sk-abc", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == ""

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_token_suffix_cleared(self, mock_get: MagicMock) -> None:
        """key 以 TOKEN 结尾的配置项 value 应被清空。"""
        mock_get.return_value = [
            {"key": "FEISHU_APP_TOKEN", "value": "tok123", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == ""

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_password_suffix_cleared(self, mock_get: MagicMock) -> None:
        """key 以 PASSWORD 结尾的配置项 value 应被清空。"""
        mock_get.return_value = [
            {"key": "DB_PASSWORD", "value": "p@ss", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == ""

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_normal_config_preserved(self, mock_get: MagicMock) -> None:
        """普通配置项（非 secret、key 不匹配敏感模式）的 value 应保留。"""
        mock_get.return_value = [
            {"key": "SITE_NAME", "value": "MySite", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == "MySite"

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_empty_list(self, mock_get: MagicMock) -> None:
        """空输入返回空列表。"""
        mock_get.return_value = []
        result = self.svc.get_default_configs()
        assert result == []

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_missing_key_treated_safely(self, mock_get: MagicMock) -> None:
        """缺少 key 字段时不应崩溃。"""
        mock_get.return_value = [
            {"value": "val", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert len(result) == 1
        # key 缺失时 str(None or "") == ""，不匹配敏感模式
        assert result[0]["value"] == "val"

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_secret_suffix_in_key_cleared(self, mock_get: MagicMock) -> None:
        """key 含 SECRET 的配置项 value 应被清空（即使 is_secret=False）。"""
        mock_get.return_value = [
            {"key": "APP_SECRET", "value": "my_secret_val", "is_secret": False},
        ]
        result = self.svc.get_default_configs()
        assert result[0]["value"] == ""

    @patch("apps.core.services.system_config_admin_service.get_default_configs")
    def test_mixed_items(self, mock_get: MagicMock) -> None:
        """混合普通和敏感配置项时分别处理。"""
        mock_get.return_value = [
            {"key": "SITE_NAME", "value": "MySite", "is_secret": False},
            {"key": "OPENAI_API_KEY", "value": "sk-abc", "is_secret": False},
            {"key": "DB_SECRET", "value": "db_secret_val", "is_secret": True},
        ]
        result = self.svc.get_default_configs()
        assert len(result) == 3
        assert result[0]["value"] == "MySite"  # 普通配置保留
        assert result[1]["value"] == ""  # API_KEY 清空
        assert result[2]["value"] == ""  # is_secret 清空
