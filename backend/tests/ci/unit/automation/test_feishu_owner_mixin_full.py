"""FeishuOwnerMixin 全覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.automation.services.chat._feishu_owner_mixin import FeishuOwnerMixin
from apps.core.exceptions import ChatCreationException, ChatProviderException, ConfigurationException


class TestFeishuOwnerMixin:
    """FeishuOwnerMixin 测试。"""

    def _make_mixin(self) -> FeishuOwnerMixin:
        mixin = FeishuOwnerMixin.__new__(FeishuOwnerMixin)
        mixin.BASE_URL = "https://open.feishu.cn/open-apis"
        mixin.ENDPOINTS = {"get_chat": "/im/v1/chats/{chat_id}"}
        mixin.config = {"TIMEOUT": 5}
        mixin.owner_config = MagicMock()
        return mixin

    # ─── is_available / _get_tenant_access_token ───

    def test_is_available_raises(self) -> None:
        mixin = self._make_mixin()
        with pytest.raises(NotImplementedError):
            mixin.is_available()

    def test_get_tenant_access_token_raises(self) -> None:
        mixin = self._make_mixin()
        with pytest.raises(NotImplementedError):
            mixin._get_tenant_access_token()

    # ─── get_chat_info ───

    def test_get_chat_info_not_available(self) -> None:
        mixin = self._make_mixin()
        mixin.is_available = MagicMock(return_value=False)
        with pytest.raises(ConfigurationException):
            mixin.get_chat_info("chat123")

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_get_chat_info_success(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin.is_available = MagicMock(return_value=True)
        mixin._get_tenant_access_token = MagicMock(return_value="token123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"name": "测试群"}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = mixin.get_chat_info("chat123")
        assert result.success is True
        assert result.chat_name == "测试群"

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_get_chat_info_api_error(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin.is_available = MagicMock(return_value=True)
        mixin._get_tenant_access_token = MagicMock(return_value="token123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 99991663, "msg": "permission denied"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(ChatProviderException):
            mixin.get_chat_info("chat123")

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_get_chat_info_http_error(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin.is_available = MagicMock(return_value=True)
        mixin._get_tenant_access_token = MagicMock(return_value="token123")
        mock_get.side_effect = httpx.HTTPError("network error")

        with pytest.raises(ChatProviderException):
            mixin.get_chat_info("chat123")

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_get_chat_info_unknown_error(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin.is_available = MagicMock(return_value=True)
        mixin._get_tenant_access_token = MagicMock(return_value="token123")
        mock_get.side_effect = RuntimeError("unknown")

        with pytest.raises(ChatProviderException):
            mixin.get_chat_info("chat123")




    # ─── _classify_feishu_error ───

    def test_classify_permission_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("99991663", "permission denied")
        assert isinstance(result, Exception)  # owner_permission_error

    def test_classify_not_found_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("99991400", "user not found")
        assert isinstance(result, Exception)

    def test_classify_validation_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("1400", "invalid parameter")
        assert isinstance(result, Exception)

    def test_classify_timeout_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("", "request timed out")
        assert isinstance(result, Exception)

    def test_classify_network_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("", "network connection failed")
        assert isinstance(result, Exception)

    def test_classify_unknown_error(self) -> None:
        mixin = self._make_mixin()
        result = mixin._classify_feishu_error("", "something else")
        assert result is ChatCreationException

    # ─── _convert_union_id_to_open_id ───

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_convert_union_id_success(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin._get_tenant_access_token = MagicMock(return_value="token")
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "data": {"user": {"open_id": "ou_open"}}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = mixin._convert_union_id_to_open_id("union_123")
        assert result == "ou_open"

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_convert_union_id_no_open_id(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin._get_tenant_access_token = MagicMock(return_value="token")
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "data": {"user": {}}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = mixin._convert_union_id_to_open_id("union_123")
        assert result is None

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_convert_union_id_api_error(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin._get_tenant_access_token = MagicMock(return_value="token")
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 9999, "msg": "error"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = mixin._convert_union_id_to_open_id("union_123")
        assert result is None

    @patch("apps.automation.services.chat._feishu_owner_mixin.httpx.get")
    def test_convert_union_id_exception(self, mock_get: MagicMock) -> None:
        mixin = self._make_mixin()
        mixin._get_tenant_access_token = MagicMock(return_value="token")
        mock_get.side_effect = RuntimeError("fail")

        result = mixin._convert_union_id_to_open_id("union_123")
        assert result is None
