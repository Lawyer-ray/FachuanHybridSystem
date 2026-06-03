"""企业微信群聊提供者单元测试"""

import re
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ChatCreationException, ConfigurationException, MessageSendException
from apps.core.models.enums import ChatPlatform


@pytest.fixture
def full_config():
    return {
        "CORP_ID": "test_corp_id",
        "AGENT_ID": "test_agent_id",
        "SECRET": "test_secret",  # pragma: allowlist secret
        "DEFAULT_OWNER_ID": "owner_user",
        "DEFAULT_MEMBER_IDS": "member_a,member_b",
        "TIMEOUT": 30,
    }


@pytest.fixture
def incomplete_config():
    return {
        "APP_KEY": "test_key",
        "TIMEOUT": 30,
    }


@pytest.fixture
def config_without_members():
    """完整配置但 DEFAULT_MEMBER_IDS 为空"""
    return {
        "CORP_ID": "test_corp_id",
        "AGENT_ID": "test_agent_id",
        "SECRET": "test_secret",  # pragma: allowlist secret
        "DEFAULT_OWNER_ID": "owner_user",
        "DEFAULT_MEMBER_IDS": "",
        "TIMEOUT": 30,
    }


def _mock_create_response(chatid="chat_001"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"errcode": 0, "chatid": chatid}
    return resp


def _mock_send_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"errcode": 0, "msgid": "msg_001"}
    return resp


class TestWeChatWorkProviderPlatform:
    """测试平台属性与可用性"""

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_platform_returns_wechat_work(self, mock_load, full_config):
        mock_load.return_value = full_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        assert WeChatWorkProvider().platform == ChatPlatform.WECHAT_WORK

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_is_available_with_full_config(self, mock_load, full_config):
        mock_load.return_value = full_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        assert WeChatWorkProvider().is_available() is True

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_is_not_available_with_incomplete_config(self, mock_load, incomplete_config):
        mock_load.return_value = incomplete_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        assert WeChatWorkProvider().is_available() is False

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_is_not_available_without_default_owner(self, mock_load):
        mock_load.return_value = {
            "CORP_ID": "c",
            "AGENT_ID": "a",
            "SECRET": "s",  # pragma: allowlist secret
            "TIMEOUT": 30,
        }
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        assert WeChatWorkProvider().is_available() is False


class TestWeChatWorkProviderCreateChat:
    """测试创建群聊"""

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_create_chat_config_incomplete_raises(self, mock_load, incomplete_config):
        mock_load.return_value = incomplete_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        with pytest.raises(ConfigurationException):
            WeChatWorkProvider().create_chat("群聊")

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_create_chat_without_owner_raises(self, mock_load):
        """有 CORP_ID/AGENT_ID/SECRET 但缺 DEFAULT_OWNER_ID → is_available()=False → ConfigurationException"""
        mock_load.return_value = {
            "CORP_ID": "c",
            "AGENT_ID": "a",
            "SECRET": "s",  # pragma: allowlist secret
            "TIMEOUT": 30,
        }
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        with pytest.raises(ConfigurationException, match="配置不完整"):
            WeChatWorkProvider().create_chat("群聊")

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_create_chat_with_members_success(self, mock_post, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        mock_post.side_effect = [_mock_create_response(), _mock_send_response()]
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        result = WeChatWorkProvider().create_chat("张三诉李四案")

        assert result.success is True
        assert result.chat_id == "chat_001"
        # 验证 payload 中 userlist 包含 owner + 两个成员（去重保序）
        create_call = mock_post.call_args_list[0]
        payload = create_call.kwargs["json"]
        assert payload["userlist"] == ["owner_user", "member_a", "member_b"]
        # 验证 chatid 合法：仅字母数字下划线连字符
        assert re.match(r"^[a-zA-Z0-9_-]+$", payload["chatid"])
        assert len(payload["chatid"]) <= 128
        assert payload["chatid"].startswith("case_")
        assert payload["owner"] == "owner_user"

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_create_chat_deduplicates_owner_in_members(self, mock_post, mock_token, mock_load):
        """owner 同时出现在 DEFAULT_MEMBER_IDS 里时应去重"""
        mock_load.return_value = {
            "CORP_ID": "c",
            "AGENT_ID": "a",
            "SECRET": "s",  # pragma: allowlist secret
            "DEFAULT_OWNER_ID": "owner_user",
            "DEFAULT_MEMBER_IDS": "owner_user,member_a",
            "TIMEOUT": 30,
        }
        mock_token.return_value = "tok_xxx"
        mock_post.side_effect = [_mock_create_response(), _mock_send_response()]
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        WeChatWorkProvider().create_chat("去重测试")
        userlist = mock_post.call_args_list[0].kwargs["json"]["userlist"]
        assert userlist.count("owner_user") == 1
        assert userlist[0] == "owner_user"
        assert "member_a" in userlist

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_create_chat_less_than_two_members_raises(self, mock_load, config_without_members):
        """DEFAULT_MEMBER_IDS 为空时 userlist 只有 owner，应抛出异常"""
        mock_load.return_value = config_without_members
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        with pytest.raises(ChatCreationException, match="至少需要 2 人"):
            WeChatWorkProvider().create_chat("人不够")

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_create_chat_with_custom_owner(self, mock_post, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        mock_post.side_effect = [_mock_create_response(), _mock_send_response()]
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        result = WeChatWorkProvider().create_chat("指定群主", owner_id="custom_owner")
        assert result.success is True
        payload = mock_post.call_args_list[0].kwargs["json"]
        assert payload["owner"] == "custom_owner"
        assert payload["userlist"][0] == "custom_owner"

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_create_chat_api_error(self, mock_post, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        error_resp = MagicMock()
        error_resp.status_code = 200
        error_resp.json.return_value = {"errcode": 301002, "errmsg": "无权限操作"}
        mock_post.return_value = error_resp
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        with pytest.raises(ChatCreationException, match="无权限操作"):
            WeChatWorkProvider().create_chat("权限不足")

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_create_chat_missing_chatid_in_response(self, mock_post, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        resp_no_chatid = MagicMock()
        resp_no_chatid.status_code = 200
        resp_no_chatid.json.return_value = {"errcode": 0}
        mock_post.return_value = resp_no_chatid
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        with pytest.raises(ChatCreationException, match="缺少群聊ID"):
            WeChatWorkProvider().create_chat("无chatid")

    def test_chatid_format_with_chinese_name(self):
        """验证中文群名生成的 chatid 无非法字符"""
        chat_name = "张三诉李四民间借贷纠纷一案"
        safe_chatid = re.sub(r"[^a-zA-Z0-9_-]", "_", f"case_{chat_name[:50]}")
        chatid = f"{safe_chatid}_{'a' * 8}"[:128]
        assert re.match(r"^[a-zA-Z0-9_-]+$", chatid)
        assert len(chatid) <= 128

    def test_chatid_truncates_to_128_chars(self):
        """超长群名的 chatid 不超过 128 字符"""
        long_name = "A" * 200
        safe_chatid = re.sub(r"[^a-zA-Z0-9_-]", "_", f"case_{long_name[:50]}")
        # 模拟实际拼接逻辑：safe_chatid 最长 55 字符(case_ + 50) + _ + 8位UUID = 64，不会超
        # 测试截断逻辑本身
        chatid = f"{safe_chatid}_{'b' * 200}"[:128]
        assert len(chatid) == 128

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_create_chat_owner_in_userlist_first_position(self, mock_load, full_config):
        """owner 始终排在 userlist 第一位"""
        mock_load.return_value = full_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        provider = WeChatWorkProvider()
        extra = provider.config.get("DEFAULT_MEMBER_IDS", "")
        initial = [m.strip() for m in extra.split(",") if m.strip()]
        userlist = list(dict.fromkeys([provider.config["DEFAULT_OWNER_ID"], *initial]))
        assert userlist[0] == "owner_user"
        assert len(userlist) == 3


class TestWeChatWorkProviderSendMessage:
    """测试发送消息"""

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    def test_send_message_config_incomplete_raises(self, mock_load, incomplete_config):
        mock_load.return_value = incomplete_config
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider
        from apps.core.dto.chat import MessageContent

        with pytest.raises(ConfigurationException):
            WeChatWorkProvider().send_message("chat_1", MessageContent(title="标题", text="内容"))

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.post")
    def test_send_message_success(self, mock_post, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        mock_post.return_value = _mock_send_response()
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider
        from apps.core.dto.chat import MessageContent

        result = WeChatWorkProvider().send_message("chat_123", MessageContent(title="法院通知", text="请查收"))
        assert result.success is True
        assert result.chat_id == "chat_123"


class TestWeChatWorkProviderGetChatInfo:
    """测试获取群聊信息"""

    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._load_config")
    @patch("apps.automation.services.chat.wechat_work_provider.WeChatWorkProvider._get_access_token")
    @patch("apps.automation.services.chat.wechat_work_provider.httpx.get")
    def test_get_chat_info_success(self, mock_get, mock_token, mock_load, full_config):
        mock_load.return_value = full_config
        mock_token.return_value = "tok_xxx"
        info_resp = MagicMock()
        info_resp.status_code = 200
        info_resp.json.return_value = {
            "errcode": 0,
            "chat_info": {"name": "测试群聊"},
        }
        mock_get.return_value = info_resp
        from apps.automation.services.chat.wechat_work_provider import WeChatWorkProvider

        result = WeChatWorkProvider().get_chat_info("chat_123")
        assert result.success is True
        assert result.chat_name == "测试群聊"
