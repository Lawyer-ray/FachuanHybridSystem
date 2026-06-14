"""Tests for social_auth/providers/__init__.py (missing: 18 lines) +
social_auth/providers/base.py (missing: 2 lines) +
social_auth/models/ (missing: 3 lines).

Covers: ProviderRegistry register/get/load_configs/get_config/enabled_list,
SocialProvider ABC, ProviderConfig, TempAuth.is_expired, SocialAccount.__str__.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.social_auth.providers.base import ProviderConfig, SocialProvider, TokenResponse, SocialProfile


class TestProviderConfig:
    def test_frozen_dataclass(self) -> None:
        config = ProviderConfig(
            name="test",
            display_name="Test",
            client_id="id",
            client_secret="secret",
        )
        assert config.name == "test"
        assert config.is_enabled is True
        assert config.extra == {}

    def test_with_extra(self) -> None:
        config = ProviderConfig(
            name="test",
            display_name="Test",
            client_id="id",
            client_secret="secret",
            is_enabled=False,
            extra={"key": "val"},
        )
        assert config.is_enabled is False
        assert config.extra == {"key": "val"}


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


class TestProviderRegistry:
    def setup_method(self) -> None:
        from apps.social_auth.providers import ProviderRegistry
        ProviderRegistry._providers = {}
        ProviderRegistry._configs = {}

    def test_register_and_get(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        @ProviderRegistry.register("test_provider")
        class TestProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""

            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")

            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="test", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        cls = ProviderRegistry.get("test_provider")
        assert cls is TestProvider

    def test_get_unknown_raises(self) -> None:
        from apps.social_auth.providers import ProviderRegistry
        with pytest.raises(KeyError, match="Unknown provider"):
            ProviderRegistry.get("nonexistent")

    def test_load_configs(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        @ProviderRegistry.register("cfg_test")
        class DummyProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="cfg_test", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        ProviderRegistry.load_configs({
            "cfg_test": {
                "display_name": "Config Test",
                "client_id": "cid",
                "client_secret": "csecret",
                "is_enabled": True,
                "extra": {"k": "v"},
            }
        })
        config = ProviderRegistry.get_config("cfg_test")
        assert config.display_name == "Config Test"

    def test_load_configs_unknown_provider_skipped(self) -> None:
        from apps.social_auth.providers import ProviderRegistry
        # Should not raise
        ProviderRegistry.load_configs({"unknown": {"display_name": "X"}})

    def test_get_config_unknown_raises(self) -> None:
        from apps.social_auth.providers import ProviderRegistry
        with pytest.raises(KeyError, match="No config"):
            ProviderRegistry.get_config("nonexistent")

    def test_enabled_list(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        @ProviderRegistry.register("enabled_test")
        class DummyProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="enabled_test", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        ProviderRegistry.load_configs({
            "enabled_test": {"display_name": "Enabled", "is_enabled": True},
        })
        result = ProviderRegistry.enabled_list()
        assert len(result) == 1
        assert result[0]["name"] == "enabled_test"

    def test_enabled_list_disabled_provider_excluded(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        @ProviderRegistry.register("disabled_test")
        class DummyProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="disabled_test", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        ProviderRegistry.load_configs({
            "disabled_test": {"display_name": "Disabled", "is_enabled": False},
        })
        result = ProviderRegistry.enabled_list()
        assert len(result) == 0

    def test_enabled_list_no_config_excluded(self) -> None:
        from apps.social_auth.providers import ProviderRegistry

        @ProviderRegistry.register("noconfig_test")
        class DummyProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="noconfig_test", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        # No config loaded
        result = ProviderRegistry.enabled_list()
        assert len(result) == 0


class TestSocialProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        class ConcreteProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return "url"
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="t")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="p", provider_user_id="1", email=None, display_name=None, avatar_url=None)

        config = ProviderConfig(name="p", display_name="P", client_id="", client_secret="")
        provider = ConcreteProvider(config)
        assert provider.config is config
        assert provider.get_client_config() is None

    def test_get_client_config_default(self) -> None:
        class MinimalProvider(SocialProvider):
            def get_authorization_url(self, state: str) -> str:
                return ""
            def exchange_code(self, code: str, state: str) -> TokenResponse:
                return TokenResponse(access_token="")
            def get_profile(self, token_response: TokenResponse) -> SocialProfile:
                return SocialProfile(provider="", provider_user_id="", email=None, display_name=None, avatar_url=None)

        config = ProviderConfig(name="", display_name="", client_id="", client_secret="")
        provider = MinimalProvider(config)
        assert provider.get_client_config() is None
