"""Coverage tests for automation.services.chat mixins (feishu, dingtalk, wechat_work)."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest


class TestFeishuTokenMixin:
    def _make(self):
        from apps.automation.services.chat._feishu_token_mixin import FeishuTokenMixin

        class Concrete(FeishuTokenMixin):
            BASE_URL = "https://open.feishu.cn"
            config = {"APP_ID": "id", "APP_SECRET": "secret", "TIMEOUT": 30}
            ENDPOINTS = {"tenant_access_token": "/open-apis/auth/v3/tenant_access_token/internal"}
            _access_token = None
            _token_expires_at = None

        return Concrete()

    def test_is_available_true(self):
        obj = self._make()
        assert obj.is_available() is True

    def test_is_available_false(self):
        obj = self._make()
        obj.config = {}
        assert obj.is_available() is False

    def test_load_config_from_db_returns_empty(self):
        obj = self._make()
        with patch("apps.core.config.utils.get_feishu_category_configs", return_value={}):
            result = obj._load_config_from_db()
            assert result == {}

    def test_load_config_from_db_with_values(self):
        obj = self._make()
        with patch("apps.core.config.utils.get_feishu_category_configs", return_value={
            "FEISHU_APP_ID": "my_id",
            "FEISHU_APP_SECRET": "my_secret",
        }):
            result = obj._load_config_from_db()
            assert result.get("APP_ID") == "my_id"

    def test_get_tenant_access_token_cached(self):
        obj = self._make()
        obj._access_token = "cached_token"
        obj._token_expires_at = datetime.now() + timedelta(hours=1)
        result = obj._get_tenant_access_token()
        assert result == "cached_token"

    def test_get_tenant_access_token_no_config(self):
        obj = self._make()
        obj._access_token = None
        obj.config = {}
        with pytest.raises(Exception):
            obj._get_tenant_access_token()


class TestDingtalkFileMixin:
    def test_get_mime_type(self):
        from apps.automation.services.chat._dingtalk_file_mixin import DingtalkFileMixin

        class Concrete(DingtalkFileMixin):
            config = {"TIMEOUT": 30}
            def is_available(self): return True
            def _get_access_token(self): return "token"

        obj = Concrete()
        assert obj._get_mime_type("test.pdf") == "application/pdf"
        assert obj._get_mime_type("test.unknown") == "application/octet-stream"

    def test_send_file_not_available(self):
        from apps.automation.services.chat._dingtalk_file_mixin import DingtalkFileMixin
        from apps.core.exceptions import ConfigurationException

        class Concrete(DingtalkFileMixin):
            config = {}
            def is_available(self): return False
            def _get_access_token(self): return ""

        obj = Concrete()
        with pytest.raises(ConfigurationException):
            obj.send_file("chat1", "/nonexistent/path")


class TestWeChatWorkFileMixin:
    def test_get_mime_type(self):
        from apps.automation.services.chat._wechat_work_file_mixin import WeChatWorkFileMixin

        class Concrete(WeChatWorkFileMixin):
            config = {"TIMEOUT": 30}
            def is_available(self): return True
            def _get_access_token(self): return "token"

        obj = Concrete()
        assert "image" in obj._get_mime_type("test.png")


class TestWeChatWorkTokenMixin:
    def test_is_available_false(self):
        from apps.automation.services.chat._wechat_work_token_mixin import WeChatWorkTokenMixin

        class Concrete(WeChatWorkTokenMixin):
            BASE_URL = ""
            config = {}
            _access_token = None
            _token_expires_at = None

        obj = Concrete()
        assert obj.is_available() is False

    def test_is_available_true(self):
        from apps.automation.services.chat._wechat_work_token_mixin import WeChatWorkTokenMixin

        class Concrete(WeChatWorkTokenMixin):
            BASE_URL = ""
            config = {"CORP_ID": "id", "AGENT_ID": "agent", "SECRET": "secret", "DEFAULT_OWNER_ID": "owner"}
            _access_token = None
            _token_expires_at = None

        obj = Concrete()
        assert obj.is_available() is True
