"""社交登录视图 / API 端点测试。

覆盖：授权页 URL 构造、回调的 state 校验与安全分支、open redirect 防护、
内嵌二维码 session 端点、以及飞书 Provider 的接口地址与错误处理。
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.test import RequestFactory

from apps.social_auth.providers.base import AuthorizationRequest, LoginMode, ProviderConfig
from apps.social_auth.providers.feishu import FeishuProvider
from apps.social_auth.providers.github import GitHubProvider
from apps.social_auth.providers.microsoft import MicrosoftProvider
from apps.social_auth.providers.wechat import WeChatProvider


class TestFeishuProvider:
    def _provider(self) -> FeishuProvider:
        return FeishuProvider(
            ProviderConfig(
                name="feishu",
                display_name="飞书",
                client_id="cli_abc",
                client_secret="fake-secret-placeholder",  # pragma: allowlist secret
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
                name="feishu",
                display_name="飞书",
                client_id="cli_abc",
                client_secret="s",
                extra={"redirect_uri": "http://x/cb"},
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
            client.post = AsyncMock(return_value=MagicMock(status_code=200, json=lambda: {"access_token": "async-tok"}))
            result = await self._provider().aexchange_code("c", self._request())
        assert result.access_token == "async-tok"


class TestWeChatProvider:
    def _provider(self) -> WeChatProvider:
        return WeChatProvider(
            ProviderConfig(
                name="wechat",
                display_name="微信",
                client_id="wx_appid",
                client_secret="fake-wx-secret-placeholder",  # pragma: allowlist secret
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


class TestGitHubProvider:
    def _provider(self) -> GitHubProvider:
        return GitHubProvider(
            ProviderConfig(
                name="github",
                display_name="GitHub",
                client_id="Iv1.abc123",
                client_secret="fake-gh-secret-placeholder",  # pragma: allowlist secret
                extra={
                    "redirect_uri": "http://localhost:8002/social/github/callback/",
                    "scope": "read:user user:email",
                },
            )
        )

    def _request(self) -> AuthorizationRequest:
        return AuthorizationRequest(
            provider="github",
            state="GHST",
            redirect_uri="http://localhost:8002/social/github/callback/",
            created_at=1.0,
        )

    def test_login_mode_is_redirect(self) -> None:
        assert self._provider().login_mode == LoginMode.REDIRECT

    def test_authorization_url(self) -> None:
        url = self._provider().get_authorization_url(self._request())
        assert url.startswith("https://github.com/login/oauth/authorize")
        assert "client_id=Iv1.abc123" in url
        assert "scope=read%3Auser%20user%3Aemail" in url
        assert "state=GHST" in url
        # GitHub 文档不列 response_type（Web 流程固定 code），不应拼进 URL
        assert "response_type" not in url
        assert "fake-gh-secret-placeholder" not in url

    def test_exchange_code_sends_accept_json_header(self) -> None:
        """GitHub 按请求头协商响应格式，缺 Accept: application/json 会返回 urlencoded 文本。"""
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200, json=lambda: {"access_token": "gho_abc", "token_type": "bearer"}
            )
            result = self._provider().exchange_code("goodcode", self._request())
            headers = mock_post.call_args.kwargs["headers"]
        assert headers["Accept"] == "application/json"
        assert result.access_token == "gho_abc"

    def test_exchange_code_rejects_error_even_on_http_200(self) -> None:
        """GitHub 对无效 code 可能返回 HTTP 200 + error body，必须识别为失败。"""
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"error": "bad_verification_code", "error_description": "The code passed is incorrect"},
            )
            with pytest.raises(ValueError, match="code passed is incorrect"):
                self._provider().exchange_code("bad", self._request())

    def test_get_profile_uses_numeric_id_and_primary_email(self) -> None:
        """身份键用数字 id（login 可改名）；私密邮箱走 /user/emails 的 primary。"""
        user_resp = MagicMock(
            status_code=200,
            json=lambda: {
                "id": 12345,
                "login": "octocat",
                "name": None,
                "email": None,
                "avatar_url": "https://avatars/x.png",
            },
        )
        emails_resp = MagicMock(
            status_code=200,
            json=lambda: [
                {"email": "secondary@example.com", "primary": False, "verified": True},
                {"email": "primary@example.com", "primary": True, "verified": True},
            ],
        )
        with patch("httpx.get", side_effect=[user_resp, emails_resp]):
            profile = self._provider().get_profile(MagicMock(access_token="gho_abc"))
        assert profile.provider == "github"
        assert profile.provider_user_id == "12345"
        # name 为空时回落 login 作为展示名
        assert profile.display_name == "octocat"
        assert profile.email == "primary@example.com"

    def test_get_profile_tolerates_emails_failure(self) -> None:
        """/user/emails 不可用（如未授权 user:email scope 返回 403）不影响登录，回落公开邮箱。"""
        user_resp = MagicMock(
            status_code=200,
            json=lambda: {"id": 12345, "login": "octocat", "name": "The Octocat", "email": "public@example.com"},
        )
        emails_resp = MagicMock(status_code=403, json=lambda: {"message": "Forbidden"})
        with patch("httpx.get", side_effect=[user_resp, emails_resp]):
            profile = self._provider().get_profile(MagicMock(access_token="gho_abc"))
        assert profile.provider_user_id == "12345"
        assert profile.email == "public@example.com"

    def test_get_profile_rejects_user_failure(self) -> None:
        user_resp = MagicMock(status_code=401, json=lambda: {"message": "Bad credentials"})
        emails_resp = MagicMock(status_code=200, json=lambda: [])
        with patch("httpx.get", side_effect=[user_resp, emails_resp]):
            with pytest.raises(ValueError, match="获取 GitHub 用户信息失败"):
                self._provider().get_profile(MagicMock(access_token="bad"))

    @pytest.mark.asyncio
    async def test_aexchange_code(self) -> None:
        with patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=MagicMock(status_code=200, json=lambda: {"access_token": "async-tok"}))
            result = await self._provider().aexchange_code("c", self._request())
        assert result.access_token == "async-tok"

    @pytest.mark.asyncio
    async def test_aget_profile(self) -> None:
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=[
                MagicMock(status_code=200, json=lambda: {"id": 7, "login": "octo", "name": None, "email": None}),
                MagicMock(
                    status_code=200, json=lambda: [{"email": "p@example.com", "primary": True, "verified": True}]
                ),
            ]
        )
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = client
            profile = await self._provider().aget_profile(MagicMock(access_token="gho_abc"))
        assert profile.provider_user_id == "7"
        assert profile.email == "p@example.com"


class TestMicrosoftProvider:
    def _provider(self) -> MicrosoftProvider:
        return MicrosoftProvider(
            ProviderConfig(
                name="microsoft",
                display_name="微软",
                client_id="ms-app-client-id",
                client_secret="fake-ms-secret-placeholder",  # pragma: allowlist secret
                extra={
                    "redirect_uri": "http://localhost:8002/social/microsoft/callback/",
                    "scope": "openid profile email",
                },
            )
        )

    def _request(self) -> AuthorizationRequest:
        return AuthorizationRequest(
            provider="microsoft",
            state="MSST",
            redirect_uri="http://localhost:8002/social/microsoft/callback/",
            created_at=1.0,
        )

    def test_login_mode_is_redirect(self) -> None:
        assert self._provider().login_mode == LoginMode.REDIRECT

    def test_endpoints_pin_common_tenant(self) -> None:
        """授权/令牌端点固定 common 租户（个人号 + 组织号通吃），userinfo 走 Graph。"""
        endpoints = MicrosoftProvider.ENDPOINTS
        assert endpoints["authorize"] == "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        assert endpoints["token"] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        assert endpoints["userinfo"] == "https://graph.microsoft.com/oidc/userinfo"

    def test_authorization_url(self) -> None:
        url = self._provider().get_authorization_url(self._request())
        assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize")
        assert "client_id=ms-app-client-id" in url
        # OIDC scope：空格必须编码为 %20
        assert "scope=openid%20profile%20email" in url
        assert "state=MSST" in url
        assert "response_mode=query" in url
        assert "fake-ms-secret-placeholder" not in url

    def test_exchange_code_sends_redirect_uri_and_rejects_error(self) -> None:
        """Entra 的 token 请求必须带与授权时一致的 redirect_uri；error body 识别为失败。"""
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "ms-token", "expires_in": 3599},
            )
            result = self._provider().exchange_code("goodcode", self._request())
            sent = mock_post.call_args.kwargs["data"]
        assert sent["redirect_uri"] == "http://localhost:8002/social/microsoft/callback/"
        assert sent["grant_type"] == "authorization_code"
        assert result.access_token == "ms-token"

        with patch("httpx.post") as mock_post_err:
            mock_post_err.return_value = MagicMock(
                status_code=400,
                json=lambda: {"error": "invalid_grant", "error_description": "code expired"},
            )
            with pytest.raises(ValueError, match="code expired"):
                self._provider().exchange_code("bad", self._request())

    def test_get_profile_uses_sub_as_identity_key(self) -> None:
        """身份键用 sub（Entra 按应用分配的稳定标识），不用可变的 email。"""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "sub": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "oid": "ffffffff-1111-2222-3333-444444444444",
                    "name": "张律师",
                    "email": "lawyer@example.com",
                    "picture": "https://graph.microsoft.com/v1.0/me/photo/$value",
                },
            )
            profile = self._provider().get_profile(MagicMock(access_token="ms-token"))
        assert profile.provider == "microsoft"
        assert profile.provider_user_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert profile.display_name == "张律师"
        assert profile.email == "lawyer@example.com"

    def test_get_profile_rejects_missing_sub(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: {"name": "无 sub"})
            with pytest.raises(ValueError, match="缺少 sub"):
                self._provider().get_profile(MagicMock(access_token="tok"))

    @pytest.mark.asyncio
    async def test_aexchange_and_aget_profile(self) -> None:
        client = MagicMock()
        client.post = AsyncMock(
            side_effect=[
                MagicMock(status_code=200, json=lambda: {"access_token": "async-ms"}),
            ]
        )
        client.get = AsyncMock(
            side_effect=[
                MagicMock(status_code=200, json=lambda: {"sub": "sub-1", "name": "A", "email": "a@x.com"}),
            ]
        )
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = client
            token = await self._provider().aexchange_code("c", self._request())
            profile = await self._provider().aget_profile(token)
        assert token.access_token == "async-ms"
        assert profile.provider_user_id == "sub-1"


class TestAuthorizationSession:
    """授权会话构建与 open redirect 防护。"""

    def _request(self) -> Any:
        rf = RequestFactory()
        req = rf.post("/api/v1/social/feishu/session", HTTP_HOST="127.0.0.1:8002")
        # 用真实 SessionStore，验证 modified 标记等行为
        from django.contrib.sessions.backends.cache import SessionStore

        req.session = SessionStore()
        return req

    def test_unknown_provider_returns_none(self) -> None:
        from apps.social_auth.views import build_authorization_session

        with patch("apps.social_auth.views.ProviderRegistry") as registry:
            registry.get.side_effect = KeyError("nope")
            assert build_authorization_session(self._request(), "does_not_exist") is None

    def test_missing_redirect_uri_returns_none(self) -> None:
        """未配置回调地址必须安全失败，而不是 KeyError 500。"""
        from apps.social_auth.views import build_authorization_session

        with patch("apps.social_auth.views.ProviderRegistry") as registry:
            registry.get.return_value = MagicMock()
            registry.get_config.return_value = ProviderConfig(
                name="feishu", display_name="飞书", client_id="cli", client_secret="s", extra={}
            )
            assert build_authorization_session(self._request(), "feishu") is None

    def test_success_writes_session(self) -> None:
        from apps.social_auth.views import build_authorization_session

        with patch("apps.social_auth.views.ProviderRegistry") as registry:
            provider_cls = MagicMock()
            provider_cls.return_value.get_authorization_url.return_value = "https://passport.feishu.cn/x"
            registry.get.return_value = provider_cls
            registry.get_config.return_value = ProviderConfig(
                name="feishu",
                display_name="飞书",
                client_id="cli_abc",
                client_secret="s",
                extra={"redirect_uri": "http://127.0.0.1:8002/social/feishu/callback/"},
            )
            req = self._request()
            session = build_authorization_session(req, "feishu", next_url="/material-prep")

        assert session is not None
        assert session.goto == "https://passport.feishu.cn/x"
        assert session.state
        # state 必须落 session，回调时才能比对
        saved = req.session.get("oauth", {})
        assert saved["state"] == session.state
        assert saved["provider"] == "feishu"
        assert saved["next_url"] == "/material-prep"
        assert saved["redirect_uri"] == "http://127.0.0.1:8002/social/feishu/callback/"
        # created_at 是 Unix 时间戳，用于回调时判断 state 是否过期
        assert saved["created_at"] > 0

    def test_sanitize_next_url(self) -> None:
        from apps.social_auth.views import sanitize_next_url

        assert sanitize_next_url("/material-prep") == "/material-prep"
        assert sanitize_next_url("/a/b?c=1&d=2") == "/a/b?c=1&d=2"

    def test_sanitize_next_url_blocks_open_redirect(self) -> None:
        from apps.social_auth.views import sanitize_next_url

        # 协议相对 URL 会被浏览器当绝对地址，必须拦
        assert sanitize_next_url("//evil.com") == "/"
        assert sanitize_next_url("https://evil.com") == "/"
        assert sanitize_next_url("javascript:alert(1)") == "/"
        assert sanitize_next_url("") == "/"
        assert sanitize_next_url(None) == "/"

    def test_frontend_callback_url(self) -> None:
        from apps.social_auth.views import _frontend_callback_url

        url = _frontend_callback_url("invalid_state")
        # 失败回调与成功回调共用 _frontend_redirect_url，因此还会带上 redirect=/；
        # 断言只关心「落到前端回调页」和「错误码原样透传」，不锁参数顺序
        assert "/social-callback?" in url
        assert "error=invalid_state" in url


class TestCallbackLoginFlow:
    """登录回调全链路：已绑定身份 → 建 TempAuth → 带 code 跳回前端。

    回归：``TempAuth.token`` 是主键却长期没有 ``default``，而回调只调
    ``acreate(user=user)``，于是每次扫码登录都在这行炸 IntegrityError
    （null value in column "token"）。因为在此之前没人真正走通过登录流程
    （未绑定时直接拒绝），这个坑一直没暴露。
    """

    def _request(self, state: str) -> Any:
        from django.contrib.sessions.backends.cache import SessionStore

        req = RequestFactory().get(
            "/social/feishu/callback/",
            {"code": "feishu-code", "state": state},
            HTTP_HOST="127.0.0.1:8002",
        )
        req.session = SessionStore()
        req.session["oauth"] = AuthorizationRequest(
            provider="feishu",
            state=state,
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
            next_url="/",
            created_at=time.time(),
        ).to_session()
        return req

    @pytest.mark.django_db
    def test_creates_tempauth_and_redirects_with_code(self) -> None:
        from apps.organization.models import LawFirm, Lawyer
        from apps.social_auth.models import SocialAccount, TempAuth
        from apps.social_auth.providers.base import SocialProfile, TokenResponse
        from apps.social_auth.views import SocialCallbackView

        firm = LawFirm.objects.create(name="回调测试律所")
        lawyer = Lawyer.objects.create_user(username="cb_lawyer", password="x", law_firm=firm)
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_cb")

        provider_cls = MagicMock()
        provider_cls.return_value.aexchange_code = AsyncMock(return_value=TokenResponse(access_token="t"))
        provider_cls.return_value.aget_profile = AsyncMock(
            return_value=SocialProfile(
                provider="feishu",
                provider_user_id="ou_cb",
                email=None,
                display_name="张三",
                avatar_url=None,
            )
        )

        state = "ST-callback"
        request = self._request(state)

        with patch("apps.social_auth.views.ProviderRegistry") as registry:
            registry.get.return_value = provider_cls
            registry.get_config.return_value = ProviderConfig(
                name="feishu",
                display_name="飞书",
                client_id="cli",
                client_secret="s",
                extra={"redirect_uri": "http://127.0.0.1:8002/social/feishu/callback/"},
            )
            response = async_to_sync(SocialCallbackView().get)(request, provider="feishu")

        assert response.status_code == 302
        location = response["Location"]
        assert "/social-callback?" in location

        temp = TempAuth.objects.get()
        assert temp.user_id == lawyer.pk
        assert temp.token is not None
        assert str(temp.token) in location
        # 用完即弃：state 不能留在 session 里被复用
        assert "oauth" not in request.session


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


class TestCreateSessionApi:
    """session 端点的入参约定。

    回归：曾因签名里声明了 Schema 参数（哪怕是空 Schema），Ninja 要求 body
    必须存在，而前端是裸 POST，导致 422「登录方式暂不可用」。
    """

    def test_signature_has_no_schema_body_param(self) -> None:
        import inspect

        from ninja import Schema

        from apps.social_auth.api.social_auth_api import create_session

        params = inspect.signature(create_session).parameters
        schema_params = [
            p for p in params.values() if isinstance(p.annotation, type) and issubclass(p.annotation, Schema)
        ]
        assert schema_params == [], "session 端点不应要求 body，否则裸 POST 会 422"

    def test_uses_lenient_rate_limit_tier(self) -> None:
        """限流档位必须是 EXPORT 而非 AUTH。

        AUTH 是 5 次/60 秒（按账密防爆破设的），而本端点只发放授权 URL、
        不校验凭据，正常用户也会因二维码过期反复刷新——用 AUTH 会把真人挡门外
        （实测前几次刷新就 429）。
        """
        import inspect

        from apps.social_auth.api.social_auth_api import create_session

        decorators = inspect.getsource(create_session).split("def create_session")[0]
        assert 'rate_limit_from_settings("EXPORT")' in decorators
        assert 'rate_limit_from_settings("AUTH")' not in decorators

    @pytest.mark.django_db
    def test_bare_post_generates_goto(self) -> None:
        """无 body、无 query 也要能生成授权 URL（前端就是这么调的）。"""
        from django.test import RequestFactory

        from apps.core.models import SystemConfig
        from apps.social_auth.api.social_auth_api import create_session
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry
        from apps.social_auth.providers.base import LoginMode, SocialProfile, SocialProvider, TokenResponse

        ProviderRegistry.register("feishu")(
            type(
                "FeishuProvider",
                (SocialProvider,),
                {
                    "ENDPOINTS": {"authorize": "https://passport.feishu.cn/suite/passport/oauth/authorize"},
                    "login_mode": LoginMode.EMBEDDED_QR,
                    "get_authorization_url": lambda self, req: f"https://passport.feishu.cn/x?state={req.state}",
                    "exchange_code": lambda self, code, req: TokenResponse(access_token=""),
                    "get_profile": lambda self, tr: SocialProfile(
                        provider="feishu", provider_user_id="1", email=None, display_name=None, avatar_url=None
                    ),
                },
            )
        )
        # 平台行不填凭证 → 借用「飞书配置」分类下的共用凭证
        SocialAuthProvider.objects.create(
            name="feishu",
            display_name="飞书",
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
        )
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu"),
                SystemConfig(key="FEISHU_APP_SECRET", value="borrowed-secret-placeholder", category="feishu"),
            ]
        )
        try:
            ProviderRegistry.clear_configs()
            req = RequestFactory().post("/api/v1/social/feishu/session", HTTP_HOST="127.0.0.1:8002")
            from django.contrib.sessions.backends.cache import SessionStore

            req.session = SessionStore()
            result = create_session(req, "feishu")
            assert result.success is True
            assert result.state
            assert result.goto
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()
            SystemConfig.objects.filter(category="feishu").delete()
            ProviderRegistry.clear_configs()
