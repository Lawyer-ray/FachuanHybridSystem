"""社交登录视图 / API 端点测试。

覆盖：授权页 URL 构造、回调的 state 校验与安全分支、open redirect 防护、
内嵌二维码 session 端点、以及飞书 Provider 的接口地址与错误处理。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.social_auth.providers.base import AuthorizationRequest, LoginMode, ProviderConfig
from apps.social_auth.providers.feishu import FeishuProvider
from apps.social_auth.providers.wechat import WeChatProvider


class TestFeishuProvider:
    def _provider(self) -> FeishuProvider:
        return FeishuProvider(
            ProviderConfig(
                name="feishu",
                display_name="飞书",
                client_id="cli_abc",
                client_secret="fake-secret-placeholder",
                extra={
                    "redirect_uri": "http://127.0.0.1:8002/social/feishu/callback/",
                    "scope": "contact:user.base:readonly",
                },
            )
        )

    def _request(self, state: str = "ST") -> AuthorizationRequest:
        return AuthorizationRequest(
            provider="feishu",
            state=state,
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
            created_at=1.0,
        )

    def test_login_mode_is_embedded_qr(self) -> None:
        assert self._provider().login_mode == LoginMode.EMBEDDED_QR

    def test_authorization_url_uses_legacy_endpoint(self) -> None:
        url = self._provider().get_authorization_url(self._request("ST123"))
        # 二维码 SDK 只支持旧流程，必须走 passport.feishu.cn
        assert url.startswith("https://passport.feishu.cn/suite/passport/oauth/authorize")
        assert "client_id=cli_abc" in url
        assert "response_type=code" in url
        assert "scope=contact:user.base:readonly" in url
        assert "state=ST123" in url

    def test_authorization_url_defaults_scope(self) -> None:
        provider = FeishuProvider(
            ProviderConfig(
                name="feishu", display_name="飞书", client_id="cli_abc", client_secret="s", extra={"redirect_uri": "http://x/cb"}
            )
        )
        assert "scope=contact:user.base:readonly" in provider.get_authorization_url(self._request())

    def test_exchange_code_rejects_rfc6749_error(self) -> None:
        """v3 令牌端点按 RFC 6749 返回 error，必须识别为失败。"""
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=400, json=lambda: {"error": "invalid_grant", "error_description": "code not found"}
            )
            with pytest.raises(ValueError, match="code not found"):
                self._provider().exchange_code("badcode", self._request())

    def test_exchange_code_success(self) -> None:
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "u-abc", "refresh_token": "r-abc", "expires_in": 7200},
            )
            result = self._provider().exchange_code("goodcode", self._request())
        assert result.access_token == "u-abc"
        assert result.refresh_token == "r-abc"

    def test_get_profile_prefers_union_id(self) -> None:
        provider = self._provider()
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "name": "张三",
                        "union_id": "on_union_123",
                        "open_id": "ou_open_456",
                        "avatar_url": "https://avatar/x.jpg",
                    },
                }
            )
            profile = provider.get_profile(MagicMock(access_token="u-abc"))
        assert profile.provider == "feishu"
        # union_id 跨应用稳定，作为账号唯一键
        assert profile.provider_user_id == "on_union_123"
        assert profile.display_name == "张三"

    def test_get_profile_falls_back_to_open_id(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {"code": 0, "msg": "success", "data": {"name": "李四", "open_id": "ou_only"}}
            )
            profile = self._provider().get_profile(MagicMock(access_token="u-abc"))
        assert profile.provider_user_id == "ou_only"

    def test_get_profile_rejects_business_error(self) -> None:
        """飞书业务错误是 HTTP 200 + code!=0，必须显式检查。"""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"code": 20005, "msg": "invalid access token"})
            with pytest.raises(ValueError, match="20005"):
                self._provider().get_profile(MagicMock(access_token="bad"))

    def test_get_client_config_excludes_secret(self) -> None:
        config = self._provider().get_client_config()
        assert config is not None
        assert config["app_id"] == "cli_abc"
        assert "secret" not in config
        assert "fake-secret-placeholder" not in str(config)

    @pytest.mark.asyncio
    async def test_aexchange_code(self) -> None:
        with patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(
                return_value=MagicMock(status_code=200, json=lambda: {"access_token": "async-tok"})
            )
            result = await self._provider().aexchange_code("c", self._request())
        assert result.access_token == "async-tok"


class TestWeChatProvider:
    def _provider(self) -> WeChatProvider:
        return WeChatProvider(
            ProviderConfig(
                name="wechat",
                display_name="微信",
                client_id="wx_appid",
                client_secret="fake-wx-secret-placeholder",
                extra={"redirect_uri": "http://127.0.0.1:8002/social/wechat/callback/"},
            )
        )

    def _request(self) -> AuthorizationRequest:
        return AuthorizationRequest(provider="wechat", state="WXST", redirect_uri="http://x/cb", created_at=1.0)

    def test_login_mode_is_redirect(self) -> None:
        assert self._provider().login_mode == LoginMode.REDIRECT

    def test_authorization_url(self) -> None:
        url = self._provider().get_authorization_url(self._request())
        assert url.startswith("https://open.weixin.qq.com/connect/qrconnect")
        assert "appid=wx_appid" in url
        assert "scope=snsapi_login" in url
        assert "state=WXST" in url
        assert url.endswith("#wechat_redirect")

    def test_exchange_code_rejects_errcode(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"errcode": 40029, "errmsg": "invalid code"})
            with pytest.raises(ValueError, match="微信授权失败"):
                self._provider().exchange_code("bad", self._request())

    def test_get_profile_uses_openid_from_raw(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"nickname": "昵称", "headimgurl": "https://a/b.jpg"})
            profile = self._provider().get_profile(MagicMock(access_token="tok", raw={"openid": "oXYZ"}))
        assert profile.provider == "wechat"
        assert profile.provider_user_id == "oXYZ"
        assert profile.display_name == "昵称"


class TestCallbackView:
    """回调视图的 state / 安全分支。"""

    def _factory(self) -> RequestFactory:
        return RequestFactory()

    def test_build_authorization_request_rejects_unknown_provider(self) -> None:
        from apps.social_auth.views import _build_authorization_request

        request, error = _build_authorization_request("does_not_exist", "/")
        assert request is None
        assert error is not None
        assert error.status_code == 400

    def test_build_authorization_request_requires_redirect_uri(self) -> None:
        """未配置回调地址必须给可读错误，而不是 KeyError 500。"""
        from apps.social_auth.views import _build_authorization_request

        with patch("apps.social_auth.views.ProviderRegistry") as mock_registry:
            mock_registry.get.return_value = MagicMock()
            mock_registry.get_config.return_value = ProviderConfig(
                name="feishu", display_name="飞书", client_id="cli", client_secret="s", extra={}
            )
            request, error = _build_authorization_request("feishu", "/")
        assert request is None
        assert error is not None
        assert "回调地址" in error.content.decode()

    def test_sanitize_next_url(self) -> None:
        from apps.social_auth.views import _sanitize_next_url

        assert _sanitize_next_url("/material-prep") == "/material-prep"
        assert _sanitize_next_url("/a/b?c=1&d=2") == "/a/b?c=1&d=2"

    def test_sanitize_next_url_blocks_open_redirect(self) -> None:
        from apps.social_auth.views import _sanitize_next_url

        # 协议相对 URL 会被浏览器当绝对地址，必须拦
        assert _sanitize_next_url("//evil.com") == "/"
        assert _sanitize_next_url("https://evil.com") == "/"
        assert _sanitize_next_url("javascript:alert(1)") == "/"
        assert _sanitize_next_url("") == "/"

    def test_frontend_callback_url(self) -> None:
        from apps.social_auth.views import _frontend_callback_url

        url = _frontend_callback_url("invalid_state")
        assert url.endswith("/social-callback?error=invalid_state")


class TestTokenExchangeApi:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_invalid_code_returns_failure(self) -> None:
        from apps.social_auth.api.social_auth_api import token_exchange
        from apps.social_auth.api.social_auth_schemas import TokenExchangeIn

        request = MagicMock()
        payload = TokenExchangeIn(code="00000000-0000-0000-0000-000000000000")
        result = await token_exchange(request, payload)
        assert result.success is False
        assert result.message
