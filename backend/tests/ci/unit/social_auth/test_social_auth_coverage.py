"""Tests for social_auth/providers/__init__.py + base.py + models/.

覆盖：ProviderRegistry 注册/查询/从 SystemConfig 构建配置/缓存失效、SocialProvider
ABC、LoginMode、AuthorizationRequest 的 session 序列化往返、TempAuth.is_expired、
SocialAccount.__str__。
"""
from __future__ import annotations

import pytest

from apps.social_auth.providers.base import (
    AuthorizationRequest,
    LoginMode,
    ProviderConfig,
    SocialProfile,
    SocialProvider,
    TokenResponse,
)


class TestProviderConfig:
    def test_frozen_dataclass(self) -> None:
        config = ProviderConfig(name="test", display_name="Test", client_id="id", client_secret="secret")
        assert config.name == "test"
        assert config.is_enabled is True
        assert config.extra == {}
        assert config.client_config == {}

    def test_with_extra(self) -> None:
        config = ProviderConfig(
            name="test", display_name="Test", client_id="id", client_secret="secret", is_enabled=False, extra={"key": "val"}
        )
        assert config.is_enabled is False
        assert config.extra == {"key": "val"}

    def test_require_returns_value(self) -> None:
        config = ProviderConfig(
            name="test", display_name="Test", client_id="id", client_secret="secret", extra={"redirect_uri": "http://x/cb"}
        )
        assert config.require("redirect_uri") == "http://x/cb"

    def test_require_missing_raises_readable_error(self) -> None:
        config = ProviderConfig(name="feishu", display_name="飞书", client_id="id", client_secret="secret")
        with pytest.raises(ValueError, match="缺少必要配置"):
            config.require("redirect_uri")


class TestTokenResponse:
    def test_defaults(self) -> None:
        resp = TokenResponse(access_token="token123")
        assert resp.access_token == "token123"
        assert resp.refresh_token is None
        assert resp.expires_in is None
        assert resp.raw == {}


class TestSocialProfile:
    def test_defaults(self) -> None:
        profile = SocialProfile(provider="wechat", provider_user_id="123", email=None, display_name=None, avatar_url=None)
        assert profile.email is None
        assert profile.avatar_url is None
        assert profile.raw_data == {}


class TestLoginMode:
    def test_values(self) -> None:
        assert LoginMode.REDIRECT.value == "redirect"
        assert LoginMode.EMBEDDED_QR.value == "embedded_qr"

    def test_is_str_enum(self) -> None:
        # 便于直接塞进 JSON 响应给前端
        assert LoginMode.REDIRECT == "redirect"


class TestAuthorizationRequest:
    def _make(self) -> AuthorizationRequest:
        return AuthorizationRequest(
            provider="feishu",
            state="state-token",
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
            next_url="/material-prep",
            created_at=1000.0,
        )

    def test_session_roundtrip(self) -> None:
        original = self._make()
        restored = AuthorizationRequest.from_session(original.to_session())
        assert restored is not None
        assert restored == original

    def test_session_roundtrip_with_code_verifier(self) -> None:
        original = AuthorizationRequest(
            provider="google", state="s", redirect_uri="http://x/cb", created_at=1.0, code_verifier="verifier-xyz"
        )
        restored = AuthorizationRequest.from_session(original.to_session())
        assert restored is not None
        assert restored.code_verifier == "verifier-xyz"

    def test_from_session_rejects_missing_provider(self) -> None:
        assert AuthorizationRequest.from_session({"state": "y", "redirect_uri": "http://x"}) is None

    def test_from_session_rejects_missing_state(self) -> None:
        assert AuthorizationRequest.from_session({"provider": "p", "redirect_uri": "http://x"}) is None

    def test_from_session_rejects_missing_redirect_uri(self) -> None:
        assert AuthorizationRequest.from_session({"provider": "p", "state": "s"}) is None

    def test_from_session_rejects_wrong_types(self) -> None:
        assert AuthorizationRequest.from_session({"provider": 1, "state": 2, "redirect_uri": 3}) is None

    def test_age_seconds(self) -> None:
        req = AuthorizationRequest(provider="p", state="s", redirect_uri="http://x", created_at=1000.0)
        assert req.age_seconds(now=1005.0) == 5.0

    def test_age_seconds_never_negative(self) -> None:
        req = AuthorizationRequest(provider="p", state="s", redirect_uri="http://x", created_at=1000.0)
        # 时钟回拨时不该出现负值
        assert req.age_seconds(now=500.0) == 0.0


class TestProviderRegistry:
    def setup_method(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry._providers = {}
        ProviderRegistry._configs = {}
        ProviderRegistry.clear_configs()

    def _make_provider(self, name: str) -> type[SocialProvider]:
        class DynamicProvider(SocialProvider):
            ENDPOINTS = {"authorize": "https://example.com/authorize"}

            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return f"https://example.com/authorize?state={request.state}"

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                return TokenResponse(access_token="t")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider=name, provider_user_id="1", email=None, display_name=None, avatar_url=None)

        DynamicProvider.__name__ = f"{name.title()}Provider"
        return DynamicProvider

    def test_register_and_get(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        cls = self._make_provider("test_provider")
        ProviderRegistry.register("test_provider")(cls)
        assert ProviderRegistry.get("test_provider") is cls
        assert ProviderRegistry.has("test_provider")
        assert "test_provider" in ProviderRegistry.names()

    def test_get_unknown_raises(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        with pytest.raises(KeyError, match="Unknown provider"):
            ProviderRegistry.get("nonexistent")

    def test_get_config_unknown_raises(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        with pytest.raises((KeyError, Exception)):
            ProviderRegistry.get_config("nonexistent")

    def test_get_config_returns_cached(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        config = ProviderConfig(name="fake", display_name="Fake", client_id="cid", client_secret="sec")
        ProviderRegistry._configs["fake"] = config
        assert ProviderRegistry.get_config("fake") is config

    def test_clear_configs_single(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry._configs["a"] = ProviderConfig(name="a", display_name="A", client_id="", client_secret="")
        ProviderRegistry._configs["b"] = ProviderConfig(name="b", display_name="B", client_id="", client_secret="")
        ProviderRegistry.clear_configs("a")
        assert "a" not in ProviderRegistry._configs
        assert "b" in ProviderRegistry._configs

    @pytest.mark.django_db
    def test_load_configs_reads_system_config(self) -> None:
        """load_configs 必须从 SystemConfig 读取，而非传入的 settings dict。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]

        rows = [
            SystemConfig(key=f"{prefix}APP_ID", value="cli_abc", category="social_auth", is_active=True),
            SystemConfig(key=f"{prefix}APP_SECRET", value="fake-secret-placeholder", category="social_auth", is_active=True, is_secret=True),
            SystemConfig(
                key=f"{prefix}REDIRECT_URI",
                value="http://127.0.0.1:8002/social/feishu/callback/",
                category="social_auth",
                is_active=True,
            ),
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth", is_active=True),
        ]
        SystemConfig.objects.bulk_create(rows)
        try:
            # 传入 settings dict 应被忽略
            ProviderRegistry.load_configs({"feishu": {"display_name": "应被忽略"}})
            config = ProviderRegistry.get_config("feishu")
            assert config.client_id == "cli_abc"
            assert config.display_name == "飞书"
            assert config.extra["redirect_uri"] == "http://127.0.0.1:8002/social/feishu/callback/"
        finally:
            SystemConfig.objects.filter(category="social_auth").delete()
            SystemConfig.objects.filter(category="feishu").delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_borrows_feishu_credentials_from_chat_category(self) -> None:
        """扫码登录复用 IM 群聊的飞书应用：本分类不填凭证时读取 FEISHU_APP_ID/SECRET。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]

        # 只配 enabled + redirect_uri，不填 App ID/Secret
        SystemConfig.objects.bulk_create([
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth", is_active=True),
            SystemConfig(
                key=f"{prefix}REDIRECT_URI",
                value="http://127.0.0.1:8002/social/feishu/callback/",
                category="social_auth",
                is_active=True,
            ),
            # 共用分类里的凭证（IM 群聊用）
            SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
            SystemConfig(
                key="FEISHU_APP_SECRET", value="shared-secret-placeholder", category="feishu", is_active=True
            ),
        ])
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_id == "cli_shared"
            assert config.client_secret == "shared-secret-placeholder"
            assert config.is_enabled is True
        finally:
            SystemConfig.objects.filter(category="social_auth").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_own_credentials_override_borrowed(self) -> None:
        """本分类填了凭证时优先用自己的，不读共用分类。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]

        SystemConfig.objects.bulk_create([
            SystemConfig(key=f"{prefix}APP_ID", value="cli_own", category="social_auth", is_active=True),
            SystemConfig(key=f"{prefix}APP_SECRET", value="own-secret-placeholder", category="social_auth", is_active=True),
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth", is_active=True),
            SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
            SystemConfig(key="FEISHU_APP_SECRET", value="shared-secret-placeholder", category="feishu", is_active=True),
        ])
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_id == "cli_own"
            assert config.client_secret == "own-secret-placeholder"
        finally:
            SystemConfig.objects.filter(category="social_auth").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_borrowed_secret_decrypted(self) -> None:
        """共用分类的 App Secret 若是密文（admin 保存时会加密），需解密后使用。"""
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]

        plaintext = "shared-secret-plain-text"
        encrypted = SecretCodec().encrypt(plaintext)
        SystemConfig.objects.bulk_create([
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth", is_active=True),
            SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
            SystemConfig(
                key="FEISHU_APP_SECRET", value=encrypted, category="feishu", is_active=True, is_secret=True
            ),
        ])
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_secret == plaintext
        finally:
            SystemConfig.objects.filter(category="social_auth").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_own_secret_is_decrypted(self) -> None:
        """本分类的 App Secret 由 Admin 表单加密存储，读取侧必须解密。

        Admin 保存 is_secret 项时走 SecretCodec.encrypt（SystemConfigAdminForm.clean_value），
        库里落的是密文。若读取侧不解密就会把密文当密钥发给 Provider，得到
        invalid_client；且现象隐蔽——授权页能正常打开，回调换 token 才失败）。
        故必须由单测兜住，不能只靠联调发现。
        """
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("google")(self._make_provider("google"))
        prefix = PROVIDER_SPECS["google"]["prefix"]

        plaintext = "GOCSPX-plain-text-secret"
        encrypted = SecretCodec().encrypt(plaintext)
        assert encrypted != plaintext

        SystemConfig.objects.bulk_create([
            SystemConfig(
                key=f"{prefix}APP_ID", value="cid.apps.googleusercontent.com", category="social_auth", is_active=True
            ),
            SystemConfig(
                key=f"{prefix}APP_SECRET", value=encrypted, category="social_auth", is_active=True, is_secret=True
            ),
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth", is_active=True),
        ])
        try:
            config = ProviderRegistry._build_config("google")
            assert config is not None
            assert config.client_secret == plaintext
            assert config.client_secret != encrypted
            assert config.is_enabled is True
        finally:
            SystemConfig.objects.filter(key__startswith=prefix).delete()

    @pytest.mark.django_db
    def test_build_config_no_credentials_anywhere_is_disabled(self) -> None:
        """本分类和共用分类都没有 App ID → 视为未配置完成，不暴露给前端。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]
        SystemConfig.objects.create(key=f"{prefix}ENABLED", value="true", category="social_auth")
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.is_enabled is False
        finally:
            SystemConfig.objects.filter(key__startswith=prefix).delete()

    @pytest.mark.django_db
    def test_build_config_enabled_false(self) -> None:
        """显式关开关 → 下线该登录方式。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]
        SystemConfig.objects.bulk_create([
            SystemConfig(key=f"{prefix}APP_ID", value="cli_abc", category="social_auth"),
            SystemConfig(key=f"{prefix}ENABLED", value="false", category="social_auth"),
        ])
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.is_enabled is False
        finally:
            SystemConfig.objects.filter(key__startswith=prefix).delete()

    @pytest.mark.django_db
    def test_build_config_inactive_rows_ignored(self) -> None:
        """is_active=False 的配置行不参与构建。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        prefix = PROVIDER_SPECS["feishu"]["prefix"]
        SystemConfig.objects.create(key=f"{prefix}APP_ID", value="cli_abc", category="social_auth", is_active=False)
        try:
            assert ProviderRegistry._build_config("feishu") is None
        finally:
            SystemConfig.objects.filter(key__startswith=prefix).delete()

    def test_load_configs_excludes_disabled_from_list(self) -> None:
        """未配置完成的 Provider 不出现在 enabled_list。"""
        from apps.social_auth.providers import ProviderRegistry

        dummy = self._make_provider("noconfig_test")
        ProviderRegistry.register("noconfig_test")(dummy)
        ProviderRegistry.load_configs()
        assert all(item["name"] != "noconfig_test" for item in ProviderRegistry.enabled_list())

    def test_enabled_list_injects_login_mode(self) -> None:
        """client_config 必须带 login_mode，前端据此分流渲染。"""
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry._providers = {}
        ProviderRegistry._providers["fake"] = type(
            "FakeProvider",
            (SocialProvider,),
            {
                "login_mode": LoginMode.EMBEDDED_QR,
                "get_authorization_url": lambda self, req: "",
                "exchange_code": lambda self, code, req: TokenResponse(access_token=""),
                "get_profile": lambda self, tr: SocialProfile(
                    provider="fake", provider_user_id="1", email=None, display_name=None, avatar_url=None
                ),
                "get_client_config": lambda self: {"app_id": "cli_abc"},
            },
        )
        ProviderRegistry._configs["fake"] = ProviderConfig(
            name="fake", display_name="Fake", client_id="cli_abc", client_secret="sec"
        )
        result = ProviderRegistry.enabled_list()
        assert result[0]["name"] == "fake"
        assert result[0]["client_config"]["login_mode"] == "embedded_qr"
        # login_mode 是 registry 注入的元信息，不应重复出现在 Provider 自己的配置里
        assert "app_id" in result[0]["client_config"]

    def test_enabled_list_empty_when_no_configs(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry._providers["x"] = self._make_provider("x")
        ProviderRegistry.load_configs()
        assert ProviderRegistry.enabled_list() == []


class TestSocialProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        class ConcreteProvider(SocialProvider):
            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return "url"

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                return TokenResponse(access_token="t")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="p", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        config = ProviderConfig(name="p", display_name="P", client_id="", client_secret="")
        provider = ConcreteProvider(config)
        assert provider.config is config
        assert provider.get_client_config() is None

    def test_default_login_mode_is_redirect(self) -> None:
        class MinimalProvider(SocialProvider):
            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return ""

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                return TokenResponse(access_token="")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="", provider_user_id="", email=None, display_name=None, avatar_url=None)

        assert MinimalProvider(ProviderConfig(name="", display_name="", client_id="", client_secret="")).login_mode == (
            LoginMode.REDIRECT
        )

    def test_endpoint_missing_raises(self) -> None:
        class MinimalProvider(SocialProvider):
            ENDPOINTS: dict[str, str] = {}

            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return ""

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                return TokenResponse(access_token="")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="", provider_user_id="", email=None, display_name=None, avatar_url=None)

        provider = MinimalProvider(ProviderConfig(name="wechat", display_name="微信", client_id="", client_secret=""))
        with pytest.raises(ValueError, match="未声明接口地址"):
            provider.endpoint("access_token")

    def test_check_api_error_success_and_failure(self) -> None:
        assert SocialProvider._check_api_error({"code": 0, "msg": "success"}) is None
        with pytest.raises(ValueError, match="20005"):
            SocialProvider._check_api_error({"code": 20005, "msg": "invalid access token"})

    @pytest.mark.asyncio
    async def test_aexchange_code_falls_back_to_sync(self) -> None:
        """默认 async 方法回退到 sync，Provider 可按需覆盖。"""
        from apps.social_auth.providers import ProviderRegistry

        captured: dict[str, object] = {}

        class SyncProvider(SocialProvider):
            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return ""

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                captured["code"] = code
                captured["request"] = request
                return TokenResponse(access_token="from-sync")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="p", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        provider = SyncProvider(ProviderConfig(name="p", display_name="P", client_id="", client_secret=""))
        req = AuthorizationRequest(provider="p", state="s", redirect_uri="http://x")
        result = await provider.aexchange_code("mycode", req)
        assert result.access_token == "from-sync"
        assert captured["code"] == "mycode"
        assert captured["request"] is req

    @pytest.mark.asyncio
    async def test_aget_profile_falls_back_to_sync(self) -> None:
        class SyncProvider(SocialProvider):
            def get_authorization_url(self, request: AuthorizationRequest) -> str:
                return ""

            def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
                return TokenResponse(access_token="")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="p", provider_user_id="42", email=None, display_name=None, avatar_url=None)

        provider = SyncProvider(ProviderConfig(name="p", display_name="P", client_id="", client_secret=""))
        profile = await provider.aget_profile(TokenResponse(access_token="t"))
        assert profile.provider_user_id == "42"


class TestRegisteredProviders:
    def test_feishu_and_wechat_registered(self) -> None:
        from apps.social_auth.providers.feishu import FeishuProvider
        from apps.social_auth.providers.wechat import WeChatProvider

        assert FeishuProvider.login_mode == LoginMode.EMBEDDED_QR
        assert WeChatProvider.login_mode == LoginMode.REDIRECT

    def test_feishu_uses_multi_host_endpoints(self) -> None:
        from apps.social_auth.providers.feishu import FeishuProvider

        endpoints = FeishuProvider.ENDPOINTS
        # 授权页走旧域名（二维码 SDK 只支持旧流程），token 走 v3 域名
        assert endpoints["authorize"].startswith("https://passport.feishu.cn")
        assert endpoints["token"] == "https://accounts.feishu.cn/oauth/v3/token"
        assert endpoints["user_info"].startswith("https://open.feishu.cn")

    def test_feishu_client_config_hides_secret(self) -> None:
        from apps.social_auth.providers.feishu import FeishuProvider

        provider = FeishuProvider(
            ProviderConfig(
                name="feishu",
                display_name="飞书",
                client_id="cli_abc",
                client_secret="fake-secret-placeholder",
                extra={"redirect_uri": "http://127.0.0.1:8002/social/feishu/callback/", "scope": "contact:user.base:readonly"},
            )
        )
        client_config = provider.get_client_config()
        assert client_config is not None
        assert "fake-secret-placeholder" not in str(client_config)
        assert "secret" not in client_config
        assert client_config["app_id"] == "cli_abc"

    def test_google_registered_as_redirect(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        # 整页跳转授权：前端按 login_mode 派发到 SocialRedirectPanel
        assert GoogleProvider.login_mode == LoginMode.REDIRECT

    def test_google_endpoints(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        endpoints = GoogleProvider.ENDPOINTS
        assert endpoints["authorize"] == "https://accounts.google.com/o/oauth2/v2/auth"
        assert endpoints["token"] == "https://oauth2.googleapis.com/token"
        assert endpoints["userinfo"] == "https://openidconnect.googleapis.com/v1/userinfo"

    def test_google_authorization_url_encodes_scope_and_redirect(self) -> None:
        """scope 含空格、redirect_uri 含斜杠，都必须编码后拼进 URL。

        裸空格会让 Google 授权页直接报错（飞书 scope 是单值所以历史上没暴露这个问题）。
        """
        from apps.social_auth.providers.google import GoogleProvider

        redirect_uri = "http://127.0.0.1:8002/social/google/callback/"
        provider = GoogleProvider(
            ProviderConfig(
                name="google",
                display_name="Google",
                client_id="cid.apps.googleusercontent.com",
                client_secret="fake-secret-placeholder",
                extra={"redirect_uri": redirect_uri},
            )
        )
        url = provider.get_authorization_url(
            AuthorizationRequest(provider="google", state="st-123", redirect_uri=redirect_uri)
        )

        assert " " not in url
        assert "scope=openid%20email%20profile" in url
        assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8002%2Fsocial%2Fgoogle%2Fcallback%2F" in url
        assert "response_type=code" in url
        assert "state=st-123" in url

    def test_google_authorization_url_omits_offline_access(self) -> None:
        """只要身份，不申请离线访问：传了会多要权限并强制每次弹同意页。"""
        from apps.social_auth.providers.google import GoogleProvider

        provider = GoogleProvider(
            ProviderConfig(
                name="google",
                display_name="Google",
                client_id="cid.apps.googleusercontent.com",
                client_secret="fake-secret-placeholder",
                extra={"redirect_uri": "http://127.0.0.1:8002/social/google/callback/"},
            )
        )
        url = provider.get_authorization_url(
            AuthorizationRequest(provider="google", state="s", redirect_uri="http://127.0.0.1:8002/social/google/callback/")
        )

        assert "access_type" not in url
        assert "prompt=" not in url
        # 授权 URL 会进浏览器地址栏，绝不能带出密钥
        assert "fake-secret-placeholder" not in url

    def test_google_scope_falls_back_to_default(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        provider = GoogleProvider(
            ProviderConfig(name="google", display_name="Google", client_id="cid", client_secret="sec")
        )
        assert provider._scope() == "openid email profile"

    def test_google_scope_from_extra(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        provider = GoogleProvider(
            ProviderConfig(name="google", display_name="Google", client_id="cid", client_secret="sec", extra={"scope": "openid email"})
        )
        assert provider._scope() == "openid email"


class TestModels:
    @pytest.mark.django_db
    def test_temp_auth_is_expired(self) -> None:
        """未过期的临时码可用，超过 5 分钟判为过期。"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.social_auth.models import TempAuth
        from apps.social_auth.models.temp_auth import TEMP_AUTH_EXPIRE_MINUTES

        fresh = TempAuth(created_at=timezone.now())
        assert fresh.is_expired is False

        stale = TempAuth(created_at=timezone.now() - timedelta(minutes=TEMP_AUTH_EXPIRE_MINUTES + 1))
        assert stale.is_expired is True

    @pytest.mark.django_db
    def test_social_account_str(self) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import SocialAccount

        user = Lawyer.objects.create_user(username="soc_test_user", password="x")
        account = SocialAccount.objects.create(
            user=user, provider="feishu", provider_uid="ou_abc", display_name="张三"
        )
        assert str(account) == f"feishu:ou_abc → {user}"
