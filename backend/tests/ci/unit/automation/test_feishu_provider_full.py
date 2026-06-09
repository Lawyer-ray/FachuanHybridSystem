"""FeishuChatProvider 全覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.automation.services.chat.feishu_provider import FeishuChatProvider
from apps.automation.services.chat.base import MessageContent
from apps.core.exceptions import (
    ChatCreationException,
    ConfigurationException,
    MessageSendException,
    OwnerSettingException,
)


class TestFeishuChatProvider:
    """FeishuChatProvider 测试。"""

    def _make_provider(self) -> FeishuChatProvider:
        """Create provider bypassing __init__."""
        p = FeishuChatProvider.__new__(FeishuChatProvider)
        p.BASE_URL = "https://open.feishu.cn/open-apis"
        p.ENDPOINTS = {
            "tenant_access_token": "/auth/v3/tenant_access_token/internal",
            "create_chat": "/im/v1/chats",
            "send_message": "/im/v1/messages",
            "upload_file": "/im/v1/files",
            "get_chat": "/im/v1/chats/{chat_id}",
        }
        p.config = {"TIMEOUT": 5}
        p._access_token = "test_token"
        p._token_expires_at = None
        p.owner_config = MagicMock()
        p.owner_config.is_validation_enabled.return_value = False
        p.owner_config.get_effective_owner_id.return_value = "ou_owner"
        return p

    # ─── platform ───

    def test_platform(self) -> None:
        p = self._make_provider()
        assert p.platform.value == "feishu"

    # ─── _build_owner_payload ───

    def test_build_owner_payload_normal(self) -> None:
        p = self._make_provider()
        payload: dict = {}
        p._build_owner_payload("ou_owner123", payload)
        assert payload["owner_id"] == "ou_owner123"
        assert payload["user_id_list"] == ["ou_owner123"]

    def test_build_owner_payload_union_id(self) -> None:
        p = self._make_provider()
        p._convert_union_id_to_open_id = MagicMock(return_value="ou_open")
        payload: dict = {}
        p._build_owner_payload("on_union123", payload)
        assert payload["owner_id"] == "ou_open"

    def test_build_owner_payload_union_id_convert_fail(self) -> None:
        p = self._make_provider()
        p._convert_union_id_to_open_id = MagicMock(return_value=None)
        payload: dict = {}
        p._build_owner_payload("on_union123", payload)
        # payload stays empty since conversion failed
        assert "owner_id" not in payload

    def test_build_owner_payload_validation_enabled(self) -> None:
        p = self._make_provider()
        p.owner_config.is_validation_enabled.return_value = True
        p.owner_config.validate_owner_id_strict = MagicMock()
        payload: dict = {}
        p._build_owner_payload("ou_owner", payload)
        p.owner_config.validate_owner_id_strict.assert_called_once()

    def test_build_owner_payload_validation_fails(self) -> None:
        p = self._make_provider()
        p.owner_config.is_validation_enabled.return_value = True
        p.owner_config.validate_owner_id_strict.side_effect = ValueError("bad id")
        payload: dict = {}
        p._build_owner_payload("ou_owner", payload)
        # Should continue despite validation failure
        assert payload["owner_id"] == "ou_owner"

    # ─── _raise_feishu_api_error ───

    def test_raise_feishu_api_error_owner_exception(self) -> None:
        p = self._make_provider()
        p._classify_feishu_error = MagicMock(return_value=OwnerSettingException(message="err"))
        with pytest.raises(OwnerSettingException):
            p._raise_feishu_api_error({"code": 99991663, "msg": "perm"}, "name", "owner", "owner", {})

    def test_raise_feishu_api_error_chat_exception(self) -> None:
        p = self._make_provider()
        p._classify_feishu_error = MagicMock(return_value=ChatCreationException)
        with pytest.raises(ChatCreationException):
            p._raise_feishu_api_error({"code": 9999, "msg": "other"}, "name", "owner", "owner", {})

    # ─── create_chat ───

    def test_create_chat_not_available(self) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=False)
        with pytest.raises(ConfigurationException):
            p.create_chat("test")

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_success(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"chat_id": "oc_123"}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = p.create_chat("测试群", owner_id="ou_owner")
        assert result.success is True
        assert result.chat_id == "oc_123"

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_api_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        p._classify_feishu_error = MagicMock(return_value=ChatCreationException)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 9999, "msg": "error"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(ChatCreationException):
            p.create_chat("测试群")

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_no_chat_id(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(ChatCreationException):
            p.create_chat("测试群")

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_http_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        mock_post.side_effect = httpx.HTTPError("network")

        from apps.core.exceptions import NetworkError
        with pytest.raises((NetworkError, OwnerSettingException)):
            p.create_chat("测试群")

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_unknown_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        mock_post.side_effect = RuntimeError("unknown")

        with pytest.raises(ChatCreationException):
            p.create_chat("测试群")

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_create_chat_without_owner(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        p.owner_config.get_effective_owner_id.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"chat_id": "oc_456"}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = p.create_chat("测试群")
        assert result.success is True

    # ─── send_message ───

    def test_send_message_not_available(self) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=False)
        with pytest.raises(ConfigurationException):
            p.send_message("chat123", MessageContent(title="", text="hi"))

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_send_message_success(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"message_id": "msg_123"}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = p.send_message("chat123", MessageContent(title="T", text="hello"))
        assert result.success is True

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_send_message_api_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 9999, "msg": "send error"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(MessageSendException):
            p.send_message("chat123", MessageContent(title="", text="hi"))

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_send_message_http_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        mock_post.side_effect = httpx.HTTPError("fail")

        with pytest.raises(MessageSendException):
            p.send_message("chat123", MessageContent(title="", text="hi"))

    @patch("apps.automation.services.chat.feishu_provider.httpx.post")
    def test_send_message_unknown_error(self, mock_post: MagicMock) -> None:
        p = self._make_provider()
        p.is_available = MagicMock(return_value=True)
        p._get_tenant_access_token = MagicMock(return_value="token")
        mock_post.side_effect = RuntimeError("boom")

        with pytest.raises(MessageSendException):
            p.send_message("chat123", MessageContent(title="", text="hi"))

    # ─── _build_simple_text_message ───

    def test_build_simple_text_title_and_text(self) -> None:
        p = self._make_provider()
        result = p._build_simple_text_message(MessageContent(title="标题", text="正文"))
        assert "标题" in result
        assert "正文" in result

    def test_build_simple_text_title_only(self) -> None:
        p = self._make_provider()
        result = p._build_simple_text_message(MessageContent(title="标题", text=""))
        assert "标题" in result

    def test_build_simple_text_text_only(self) -> None:
        p = self._make_provider()
        result = p._build_simple_text_message(MessageContent(title="", text="正文"))
        assert result == "正文"

    def test_build_simple_text_empty(self) -> None:
        p = self._make_provider()
        result = p._build_simple_text_message(MessageContent(title="", text=""))
        assert result == "空消息"

    # ─── _build_rich_text_message ───

    def test_build_rich_text_both(self) -> None:
        p = self._make_provider()
        result = p._build_rich_text_message(MessageContent(title="T", text="B"))
        assert len(result["elements"]) == 3  # title + hr + text

    def test_build_rich_text_title_only(self) -> None:
        p = self._make_provider()
        result = p._build_rich_text_message(MessageContent(title="T", text=""))
        assert len(result["elements"]) == 1

    def test_build_rich_text_empty(self) -> None:
        p = self._make_provider()
        result = p._build_rich_text_message(MessageContent(title="", text=""))
        assert len(result["elements"]) == 0
