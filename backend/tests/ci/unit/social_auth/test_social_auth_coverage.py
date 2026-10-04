"""Tests for social_auth/providers/__init__.py + base.py + models/.

覆盖：ProviderRegistry 注册/查询/从 SystemConfig 构建配置/缓存失效、SocialProvider
ABC、LoginMode、AuthorizationRequest 的 session 序列化往返、TempAuth.is_expired、
SocialAccount.__str__。
"""

from __future__ import annotations

import time

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
        config = ProviderConfig(
            name="test", display_name="Test", client_id="id", client_secret="secret"
        )  # pragma: allowlist secret
        assert config.name == "test"
        assert config.is_enabled is True
        assert config.extra == {}
        assert config.client_config == {}

    def test_with_extra(self) -> None:
        config = ProviderConfig(
            name="test",
            display_name="Test",
            client_id="id",
            client_secret="secret",  # pragma: allowlist secret
            is_enabled=False,
            extra={"key": "val"},
        )
        assert config.is_enabled is False
        assert config.extra == {"key": "val"}

    def test_require_returns_value(self) -> None:
        config = ProviderConfig(
            name="test",
            display_name="Test",
            client_id="id",
            client_secret="secret",  # pragma: allowlist secret
            extra={"redirect_uri": "http://x/cb"},
        )
        assert config.require("redirect_uri") == "http://x/cb"

    def test_require_missing_raises_readable_error(self) -> None:
        config = ProviderConfig(
            name="feishu", display_name="飞书", client_id="id", client_secret="secret"
        )  # pragma: allowlist secret
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
        profile = SocialProfile(
            provider="wechat", provider_user_id="123", email=None, display_name=None, avatar_url=None
        )
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
                return SocialProfile(
                    provider=name, provider_user_id="1", email=None, display_name=None, avatar_url=None
                )

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

        config = ProviderConfig(
            name="fake", display_name="Fake", client_id="cid", client_secret="sec"
        )  # pragma: allowlist secret
        ProviderRegistry._configs["fake"] = config
        # 手动注入的缓存要补时钟戳，否则 get_config 的 TTL 兜底会判过期去查库
        # （本用例无 django_db 标记，查库即错）
        ProviderRegistry._configs_loaded_at = time.monotonic()
        assert ProviderRegistry.get_config("fake") is config

    def test_clear_configs_clears_all(self) -> None:
        """一律整体清空，不做按名局部失效。

        局部失效与「缓存为空才重建」这个判断天然矛盾，会让新启用的 Provider 在
        列表接口长期缺席（回归见 test_newly_enabled_provider_appears_after_invalidation）。
        """
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry._configs["a"] = ProviderConfig(name="a", display_name="A", client_id="", client_secret="")
        ProviderRegistry._configs["b"] = ProviderConfig(name="b", display_name="B", client_id="", client_secret="")
        ProviderRegistry.clear_configs()
        assert ProviderRegistry._configs == {}

    @pytest.mark.django_db
    def test_newly_enabled_provider_appears_after_invalidation(self) -> None:
        """运行中启用新 Provider 后，列表接口必须立刻能看到它。

        回归（2026-09-27 实测）：缓存里已有 feishu 时，按名清掉 google 后缓存仍非空，
        列表接口便不再重建，绑定页一直显示「该登录方式暂未开放」，必须重启后端。
        这里通过创建 provider 行触发真实的 post_save 信号失效。
        """
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        ProviderRegistry.register("google")(self._make_provider("google"))

        SocialAuthProvider.objects.create(name="feishu", display_name="飞书", client_id="cli_f", client_secret="sec-f")
        try:
            ProviderRegistry.load_configs()
            assert [item["name"] for item in ProviderRegistry.enabled_list()] == ["feishu"]

            # 运行中补上 Google 凭证（等同在 admin 里填完保存），post_save 信号整体失效缓存
            SocialAuthProvider.objects.create(
                name="google", display_name="Google", client_id="cid.apps.googleusercontent.com", client_secret="sec-g"
            )

            assert "google" in [item["name"] for item in ProviderRegistry.enabled_list()]
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_stale_cache_picks_up_cross_process_write(self) -> None:
        """跨进程写库收不到信号（manage.py 脚本直写 / 多 worker 部署），TTL 到期后必须自动看到新凭证。

        回归（2026-10-04 实测）：从脚本直写配置后，运行中后端缓存非空
        不重建，绑定页长期显示「该登录方式暂未开放」，只能重启。本用例不触发
        信号（bulk_create 不发 post_save），完全依赖 TTL 兜底。
        """
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import _CONFIG_TTL_SECONDS, ProviderRegistry

        def enabled_names() -> list[str]:
            return [item["name"] for item in ProviderRegistry.enabled_list()]

        # setup_method 会清空注册表（类内惯例），先注册本用例需要的两个名字
        ProviderRegistry.register("google")(self._make_provider("google"))
        ProviderRegistry.register("github")(self._make_provider("github"))

        try:
            SocialAuthProvider.objects.create(
                name="google", display_name="Google", client_id="cid-g", client_secret="sec-g"
            )
            ProviderRegistry.load_configs()
            assert enabled_names() == ["google"]

            # 另一个进程直写 GitHub 凭证：bulk_create 不发 post_save 信号，
            # 本进程收不到任何通知，TTL 内仍读旧缓存
            SocialAuthProvider.objects.bulk_create(
                [SocialAuthProvider(name="github", display_name="GitHub", client_id="Iv1.gh", client_secret="sec-gh")]
            )
            assert "github" not in enabled_names()

            # 时间越过 TTL（模拟 30 秒后），下一次读取自动重建
            ProviderRegistry._configs_loaded_at -= _CONFIG_TTL_SECONDS + 1
            assert "github" in enabled_names()
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_get_config_refreshes_stale_credentials(self) -> None:
        """已缓存的 Provider 在 TTL 过期后也要拿到跨进程改过的新值（get_config 自带 TTL 兜底）。"""
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import _CONFIG_TTL_SECONDS, ProviderRegistry

        ProviderRegistry.register("google")(self._make_provider("google"))

        try:
            SocialAuthProvider.objects.create(
                name="google", display_name="Google", client_id="cid-old", client_secret="sec-g"
            )
            ProviderRegistry.load_configs()
            assert ProviderRegistry.get_config("google").client_id == "cid-old"

            # 跨进程换凭证（.update() 不触发信号）：TTL 内仍是旧值
            SocialAuthProvider.objects.filter(name="google").update(client_id="cid-new")
            assert ProviderRegistry.get_config("google").client_id == "cid-old"

            ProviderRegistry._configs_loaded_at -= _CONFIG_TTL_SECONDS + 1
            assert ProviderRegistry.get_config("google").client_id == "cid-new"
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_load_configs_reads_provider_table(self) -> None:
        """load_configs 必须从 SocialAuthProvider 表读取，而非传入的 settings dict。"""
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))

        SocialAuthProvider.objects.create(
            name="feishu",
            display_name="飞书",
            client_id="cli_abc",
            client_secret="fake-secret-placeholder",  # pragma: allowlist secret
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
            scope="contact:user.base:readonly",
        )
        try:
            # 传入 settings dict 应被忽略
            ProviderRegistry.load_configs({"feishu": {"display_name": "应被忽略"}})
            config = ProviderRegistry.get_config("feishu")
            assert config.client_id == "cli_abc"
            assert config.display_name == "飞书"
            assert config.extra["redirect_uri"] == "http://127.0.0.1:8002/social/feishu/callback/"
            assert config.extra["scope"] == "contact:user.base:readonly"
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_secret_stored_encrypted_in_db(self) -> None:
        """client_secret 落库必须加密：库里是密文，读出来是明文。

        这是独立成表（EncryptedTextField 模型层加密）相对 SystemConfig
        （表单层加密 + 读取侧手动解密）的核心安全收益——密文当密钥发给
        Provider 会得到 invalid_client，且现象隐蔽（授权页正常、回调才失败）。
        """
        from django.db import connection

        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("google")(self._make_provider("google"))
        SocialAuthProvider.objects.create(
            name="google", display_name="Google", client_id="cid", client_secret="plain-secret-value"
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT client_secret FROM social_auth_socialauthprovider WHERE name = %s", ["google"])
                raw = str(cursor.fetchone()[0] or "")
            assert raw.startswith("enc:v1:")
            assert "plain-secret-value" not in raw

            config = ProviderRegistry._build_config("google")
            assert config is not None
            assert config.client_secret == "plain-secret-value"  # pragma: allowlist secret
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_enabled_list_orders_by_priority(self) -> None:
        """登录页按钮顺序由 priority 决定，小的在前。"""
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("google")(self._make_provider("google"))
        ProviderRegistry.register("github")(self._make_provider("github"))

        SocialAuthProvider.objects.create(
            name="github", display_name="GitHub", client_id="gh", client_secret="s", priority=5
        )
        SocialAuthProvider.objects.create(
            name="google", display_name="Google", client_id="gg", client_secret="s", priority=20
        )
        try:
            assert [item["name"] for item in ProviderRegistry.enabled_list()] == ["github", "google"]
        finally:
            SocialAuthProvider.objects.all().delete()
            ProviderRegistry.clear_configs()

    @pytest.mark.django_db
    def test_borrows_feishu_credentials_from_chat_category(self) -> None:
        """扫码登录复用 IM 群聊的飞书应用：平台行不填凭证时读取 FEISHU_APP_ID/SECRET。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))

        SocialAuthProvider.objects.create(
            name="feishu",
            display_name="飞书",
            redirect_uri="http://127.0.0.1:8002/social/feishu/callback/",
        )
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
                SystemConfig(
                    key="FEISHU_APP_SECRET", value="shared-secret-placeholder", category="feishu", is_active=True
                ),
            ]
        )
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_id == "cli_shared"
            assert config.client_secret == "shared-secret-placeholder"  # pragma: allowlist secret
            assert config.is_enabled is True
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_own_credentials_override_borrowed(self) -> None:
        """平台行填了凭证时优先用自己的，不读共用分类。"""
        from apps.core.models import SystemConfig
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))

        SocialAuthProvider.objects.create(
            name="feishu", display_name="飞书", client_id="cli_own", client_secret="own-secret-placeholder"
        )
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
                SystemConfig(
                    key="FEISHU_APP_SECRET", value="shared-secret-placeholder", category="feishu", is_active=True
                ),
            ]
        )
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_id == "cli_own"
            assert config.client_secret == "own-secret-placeholder"  # pragma: allowlist secret
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_borrowed_secret_decrypted(self) -> None:
        """共用分类的 App Secret 若是密文（admin 保存时会加密），需解密后使用。"""
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))

        plaintext = "shared-secret-plain-text"
        encrypted = SecretCodec().encrypt(plaintext)
        SocialAuthProvider.objects.create(name="feishu", display_name="飞书")
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu", is_active=True),
                SystemConfig(
                    key="FEISHU_APP_SECRET", value=encrypted, category="feishu", is_active=True, is_secret=True
                ),
            ]
        )
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.client_secret == plaintext
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()
            SystemConfig.objects.filter(category="feishu").delete()

    @pytest.mark.django_db
    def test_own_secret_is_decrypted(self) -> None:
        """本表 client_secret 由 EncryptedTextField 模型层加密存储，读取侧天然拿到明文。

        历史上（SystemConfig 时代）靠读取侧手动解密兜住「密文当密钥」的坑；
        独立成表后由字段层保证，本用例持续锁住这个行为。
        """
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("google")(self._make_provider("google"))

        SocialAuthProvider.objects.create(
            name="google",
            display_name="Google",
            client_id="cid.apps.googleusercontent.com",
            client_secret="GOCSPX-plain-text-secret",  # pragma: allowlist secret
        )
        try:
            config = ProviderRegistry._build_config("google")
            assert config is not None
            assert config.client_secret == "GOCSPX-plain-text-secret"  # pragma: allowlist secret
            assert config.is_enabled is True
        finally:
            SocialAuthProvider.objects.filter(name="google").delete()

    @pytest.mark.django_db
    def test_build_config_no_credentials_anywhere_is_disabled(self) -> None:
        """本表和共用分类都没有 client_id → 视为未配置完成，不暴露给前端。"""
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        SocialAuthProvider.objects.create(name="feishu", display_name="飞书")
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.is_enabled is False
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()

    @pytest.mark.django_db
    def test_build_config_enabled_false(self) -> None:
        """显式关开关 → 下线该登录方式。"""
        from apps.social_auth.models import SocialAuthProvider
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        SocialAuthProvider.objects.create(
            name="feishu", display_name="飞书", client_id="cli_abc", client_secret="s", enabled=False
        )
        try:
            config = ProviderRegistry._build_config("feishu")
            assert config is not None
            assert config.is_enabled is False
        finally:
            SocialAuthProvider.objects.filter(name="feishu").delete()

    @pytest.mark.django_db
    def test_build_config_without_row_returns_none(self) -> None:
        """库里没有该平台的行 → 视为未接入，返回 None。"""
        from apps.social_auth.providers import ProviderRegistry

        ProviderRegistry.register("feishu")(self._make_provider("feishu"))
        assert ProviderRegistry._build_config("feishu") is None

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
            name="fake",
            display_name="Fake",
            client_id="cli_abc",
            client_secret="sec",  # pragma: allowlist secret
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
                return SocialProfile(
                    provider="p", provider_user_id="42", email=None, display_name=None, avatar_url=None
                )

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
        """飞书的接口散在三个域名下，不能假设只有一个 BASE_URL。

        断言比 urlparse 的 hostname 而不是 startswith —— 后者会把
        ``https://passport.feishu.cn.evil.example`` 也判为通过
        （CodeQL 的 incomplete-url-substring-sanitization 规则会报这一点）。
        """
        from urllib.parse import urlparse

        from apps.social_auth.providers.feishu import FeishuProvider

        endpoints = FeishuProvider.ENDPOINTS
        # 授权页走旧域名（二维码 SDK 只支持旧流程），token 走 v3 域名
        assert urlparse(endpoints["authorize"]).hostname == "passport.feishu.cn"
        assert endpoints["token"] == "https://accounts.feishu.cn/oauth/v3/token"
        assert urlparse(endpoints["user_info"]).hostname == "open.feishu.cn"

    def test_feishu_client_config_hides_secret(self) -> None:
        from apps.social_auth.providers.feishu import FeishuProvider

        provider = FeishuProvider(
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
                client_secret="fake-secret-placeholder",  # pragma: allowlist secret
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
                client_secret="fake-secret-placeholder",  # pragma: allowlist secret
                extra={"redirect_uri": "http://127.0.0.1:8002/social/google/callback/"},
            )
        )
        url = provider.get_authorization_url(
            AuthorizationRequest(
                provider="google", state="s", redirect_uri="http://127.0.0.1:8002/social/google/callback/"
            )
        )

        assert "access_type" not in url
        assert "prompt=" not in url
        # 授权 URL 会进浏览器地址栏，绝不能带出密钥
        assert "fake-secret-placeholder" not in url

    def test_google_scope_falls_back_to_default(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        provider = GoogleProvider(
            ProviderConfig(
                name="google", display_name="Google", client_id="cid", client_secret="sec"
            )  # pragma: allowlist secret
        )
        assert provider._scope() == "openid email profile"

    def test_google_scope_from_extra(self) -> None:
        from apps.social_auth.providers.google import GoogleProvider

        provider = GoogleProvider(
            ProviderConfig(
                name="google",
                display_name="Google",
                client_id="cid",
                client_secret="sec",  # pragma: allowlist secret
                extra={"scope": "openid email"},
            )
        )
        assert provider._scope() == "openid email"

    def test_github_registered_as_redirect(self) -> None:
        from apps.social_auth.providers.github import GitHubProvider

        # 整页跳转授权：前端按 login_mode 派发到 SocialRedirectPanel
        assert GitHubProvider.login_mode == LoginMode.REDIRECT

    def test_microsoft_registered_as_redirect(self) -> None:
        from apps.social_auth.providers.microsoft import MicrosoftProvider

        assert MicrosoftProvider.login_mode == LoginMode.REDIRECT

    @pytest.mark.django_db
    def test_microsoft_default_row_created_by_migration(self) -> None:
        """迁移 0007 为微软插入默认配置行：client_id 留空 → 登录页不显示，admin 可填。"""
        from django.apps import apps

        from apps.social_auth.migrations._microsoft_helpers import add_microsoft_provider, remove_microsoft_provider

        SocialAuthProvider = apps.get_model("social_auth", "SocialAuthProvider")
        try:
            add_microsoft_provider(apps, None)
            row = SocialAuthProvider.objects.get(name="microsoft")
            assert row.display_name == "微软"
            assert row.enabled is True
            assert row.priority == 35
            assert (row.client_id or "") == ""

            add_microsoft_provider(apps, None)
            assert SocialAuthProvider.objects.filter(name="microsoft").count() == 1

            remove_microsoft_provider(apps, None)
            assert not SocialAuthProvider.objects.filter(name="microsoft").exists()
        finally:
            SocialAuthProvider.objects.filter(name="microsoft").delete()

    def test_microsoft_in_provider_specs_without_fallback(self) -> None:
        from apps.social_auth.providers import PROVIDER_SPECS

        spec = PROVIDER_SPECS["microsoft"]
        assert spec["display_name"] == "微软"
        assert "fallback_credentials" not in spec

    def test_github_endpoints(self) -> None:
        from apps.social_auth.providers.github import GitHubProvider

        endpoints = GitHubProvider.ENDPOINTS
        assert endpoints["authorize"] == "https://github.com/login/oauth/authorize"
        assert endpoints["token"] == "https://github.com/login/oauth/access_token"
        assert endpoints["userinfo"] == "https://api.github.com/user"
        assert endpoints["emails"] == "https://api.github.com/user/emails"

    def test_github_authorization_url_encodes_scope_and_redirect(self) -> None:
        """scope 含空格与冒号、redirect_uri 含斜杠，都必须编码后拼进 URL。"""
        from apps.social_auth.providers.github import GitHubProvider

        redirect_uri = "http://127.0.0.1:8002/social/github/callback/"
        provider = GitHubProvider(
            ProviderConfig(
                name="github",
                display_name="GitHub",
                client_id="Iv1.abc123",
                client_secret="fake-secret-placeholder",  # pragma: allowlist secret
                extra={"redirect_uri": redirect_uri},
            )
        )
        url = provider.get_authorization_url(
            AuthorizationRequest(provider="github", state="st-123", redirect_uri=redirect_uri)
        )

        assert " " not in url
        assert "scope=read%3Auser%20user%3Aemail" in url
        assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8002%2Fsocial%2Fgithub%2Fcallback%2F" in url
        assert "state=st-123" in url
        # 授权 URL 会进浏览器地址栏，绝不能带出密钥
        assert "fake-secret-placeholder" not in url

    def test_github_scope_falls_back_to_default(self) -> None:
        from apps.social_auth.providers.github import GitHubProvider

        provider = GitHubProvider(
            ProviderConfig(
                name="github", display_name="GitHub", client_id="cid", client_secret="sec"
            )  # pragma: allowlist secret
        )
        assert provider._scope() == "read:user user:email"

    def test_github_scope_from_extra(self) -> None:
        from apps.social_auth.providers.github import GitHubProvider

        provider = GitHubProvider(
            ProviderConfig(
                name="github",
                display_name="GitHub",
                client_id="cid",
                client_secret="sec",  # pragma: allowlist secret
                extra={"scope": "read:user"},
            )
        )
        assert provider._scope() == "read:user"


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
        account = SocialAccount.objects.create(user=user, provider="feishu", provider_uid="ou_abc", display_name="张三")
        assert str(account) == f"feishu:ou_abc → {user}"
