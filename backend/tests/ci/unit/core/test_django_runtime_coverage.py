"""Tests for core config.django_runtime module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from apps.core.config.django_runtime import (
    DjangoSecurityConfig,
    _env_bool,
    _resolve_secret_key,
    _split_csv,
    resolve_cache_redis_url,
    resolve_channel_layers,
    resolve_channel_redis_url,
    resolve_contract_folder_browse_roots,
    resolve_cors_and_csrf,
    resolve_perm_open_access,
    resolve_q_cluster,
    resolve_rate_limit,
    resolve_redis_url,
    resolve_security_config,
)

# 测试专用占位密钥（非真实密钥，dev 模式下仅验证解析逻辑）
_TEST_DEV_SECRET_KEY = "test-only-dev-secret-key"  # pragma: allowlist secret
_TEST_FAKE_FERNET_KEY = Fernet.generate_key().decode()


class TestEnvBool:
    @patch.dict(os.environ, {"TEST_VAR": "true"})
    def test_true(self) -> None:
        assert _env_bool("TEST_VAR") is True

    @patch.dict(os.environ, {"TEST_VAR": "1"})
    def test_one(self) -> None:
        assert _env_bool("TEST_VAR") is True

    @patch.dict(os.environ, {"TEST_VAR": "yes"})
    def test_yes(self) -> None:
        assert _env_bool("TEST_VAR") is True

    @patch.dict(os.environ, {"TEST_VAR": "false"})
    def test_false(self) -> None:
        assert _env_bool("TEST_VAR") is False

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_returns_default(self) -> None:
        assert _env_bool("NONEXISTENT_VAR") is False
        assert _env_bool("NONEXISTENT_VAR", default=True) is True

    @patch.dict(os.environ, {"TEST_VAR": ""})
    def test_empty_returns_default(self) -> None:
        assert _env_bool("TEST_VAR", default=True) is True

    @patch.dict(os.environ, {"TEST_VAR": " yes "})
    def test_strips_whitespace(self) -> None:
        assert _env_bool("TEST_VAR") is True


class TestSplitCsv:
    def test_basic(self) -> None:
        assert _split_csv("a,b,c") == ["a", "b", "c"]

    def test_with_spaces(self) -> None:
        assert _split_csv(" a , b , c ") == ["a", "b", "c"]

    def test_empty(self) -> None:
        assert _split_csv("") == []

    def test_none(self) -> None:
        assert _split_csv(None) == []  # type: ignore[arg-type]


class TestResolveSecretKey:
    @patch.dict(os.environ, {"DJANGO_DEBUG": "true"}, clear=False)
    def test_dev_mode_uses_fallback(self) -> None:
        result = _resolve_secret_key(False, "dev-secret")
        # In dev mode with no env var, uses dev_secret_key
        assert isinstance(result, str)

    @patch.dict(os.environ, {"DJANGO_SECRET_KEY": "a-very-long-secret-key-that-is-at-least-50-characters-long!!"})  # pragma: allowlist secret
    def test_production_valid_key(self) -> None:
        result = _resolve_secret_key(True, "dev-secret")
        assert "long-secret" in result

    @patch.dict(os.environ, {"DJANGO_SECRET_KEY": "short"}, clear=False)  # pragma: allowlist secret
    def test_production_short_key_raises(self) -> None:
        with pytest.raises(RuntimeError, match="DJANGO_SECRET_KEY"):
            _resolve_secret_key(True, "dev-secret")

    @patch.dict(os.environ, {"DJANGO_SECRET_KEY": ""}, clear=False)
    def test_production_empty_key_raises(self) -> None:
        with pytest.raises(RuntimeError, match="DJANGO_SECRET_KEY"):
            _resolve_secret_key(True, "dev-secret")


class TestResolveRateLimit:
    def test_returns_all_keys(self) -> None:
        result = resolve_rate_limit()
        assert "DEFAULT_REQUESTS" in result
        assert "AUTH_REQUESTS" in result
        assert "LLM_REQUESTS" in result


class TestResolveRedisUrl:
    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    def test_with_redis_url(self) -> None:
        assert resolve_redis_url() == "redis://localhost:6379/0"

    @patch.dict(os.environ, {}, clear=True)
    def test_without_redis_url(self) -> None:
        # Remove REDIS_URL if set
        os.environ.pop("REDIS_URL", None)
        os.environ.pop("DJANGO_CACHE_REDIS_URL", None)
        assert resolve_redis_url() == ""


class TestResolveCacheRedisUrl:
    @patch.dict(os.environ, {"DJANGO_CACHE_REDIS_URL": "redis://cache:6379/0"})
    def test_dedicated_overrides_base(self) -> None:
        assert resolve_cache_redis_url() == "redis://cache:6379/0"

    @patch.dict(os.environ, {"REDIS_URL": "redis://base:6379/0"}, clear=False)
    def test_falls_back_to_base(self) -> None:
        os.environ.pop("DJANGO_CACHE_REDIS_URL", None)
        assert resolve_cache_redis_url() == "redis://base:6379/0"


class TestResolveChannelRedisUrl:
    @patch.dict(os.environ, {"DJANGO_CHANNEL_REDIS_URL": "redis://channel:6379/0"})
    def test_dedicated(self) -> None:
        assert resolve_channel_redis_url() == "redis://channel:6379/0"


class TestResolveChannelLayers:
    @patch.dict(os.environ, {"DJANGO_CHANNEL_REDIS_URL": "redis://localhost:6379/0"})
    def test_with_redis(self) -> None:
        result = resolve_channel_layers()
        assert result["default"]["BACKEND"] == "channels_redis.core.RedisChannelLayer"

    @patch.dict(os.environ, {}, clear=True)
    def test_without_redis(self) -> None:
        os.environ.pop("DJANGO_CHANNEL_REDIS_URL", None)
        os.environ.pop("REDIS_URL", None)
        result = resolve_channel_layers()
        assert result["default"]["BACKEND"] == "channels.layers.InMemoryChannelLayer"


class TestResolveQCluster:
    def test_returns_base_config(self) -> None:
        result = resolve_q_cluster()
        assert "name" in result
        assert "workers" in result

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    def test_with_redis(self) -> None:
        result = resolve_q_cluster()
        assert "redis" in result

    @patch.dict(os.environ, {}, clear=True)
    def test_without_redis(self) -> None:
        os.environ.pop("REDIS_URL", None)
        result = resolve_q_cluster()
        assert "orm" in result


class TestResolvePermOpenAccess:
    @patch.dict(os.environ, {"PERM_OPEN_ACCESS": "true"})
    def test_dev_enabled(self) -> None:
        assert resolve_perm_open_access(is_production=False) is True

    @patch.dict(os.environ, {"PERM_OPEN_ACCESS": "false"})
    def test_dev_disabled(self) -> None:
        assert resolve_perm_open_access(is_production=False) is False

    @patch.dict(os.environ, {"PERM_OPEN_ACCESS": ""})
    def test_dev_empty(self) -> None:
        assert resolve_perm_open_access(is_production=False) is False

    @patch.dict(os.environ, {"PERM_OPEN_ACCESS": "true"})
    def test_prod_enabled_raises(self) -> None:
        with pytest.raises(RuntimeError, match="生产环境"):
            resolve_perm_open_access(is_production=True)

    @patch.dict(os.environ, {"PERM_OPEN_ACCESS": ""})
    def test_prod_disabled(self) -> None:
        assert resolve_perm_open_access(is_production=True) is False


class TestResolveCorsAndCsrf:
    def test_debug_mode(self) -> None:
        result = resolve_cors_and_csrf(debug=True, allow_lan=False, safe_cors_origins=["http://localhost:3000"])
        assert result["CORS_ALLOW_ALL_ORIGINS"] is False
        assert "http://localhost:3000" in result["CORS_ALLOWED_ORIGINS"]

    @patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://example.com", "CSRF_TRUSTED_ORIGINS": "https://example.com"})
    def test_production_mode(self) -> None:
        result = resolve_cors_and_csrf(debug=False, allow_lan=False, safe_cors_origins=[])
        assert "https://example.com" in result["CORS_ALLOWED_ORIGINS"]

    @patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "", "CSRF_TRUSTED_ORIGINS": ""})
    def test_production_no_origins_raises(self) -> None:
        with pytest.raises(RuntimeError, match="生产环境"):
            resolve_cors_and_csrf(debug=False, allow_lan=False, safe_cors_origins=[])

    @patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://lan.local", "CSRF_TRUSTED_ORIGINS": "https://lan.local"})
    def test_allow_lan(self) -> None:
        result = resolve_cors_and_csrf(debug=False, allow_lan=True, safe_cors_origins=[])
        assert "https://lan.local" in result["CORS_ALLOWED_ORIGINS"]

    @patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "", "CSRF_TRUSTED_ORIGINS": ""})
    def test_allow_lan_no_origins_raises(self) -> None:
        with pytest.raises(RuntimeError, match="DJANGO_ALLOW_LAN"):
            resolve_cors_and_csrf(debug=False, allow_lan=True, safe_cors_origins=[])


class TestResolveSecurityConfig:
    @patch.dict(os.environ, {"DJANGO_ALLOW_LAN": "False"})
    def test_dev_mode_uses_default_allowed_hosts(self) -> None:
        result = resolve_security_config(
            dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["prod.example"]
        )
        assert result.debug is True
        assert result.allowed_hosts == ["*"]

    @patch.dict(os.environ, {"DJANGO_ALLOW_LAN": "False"})
    def test_prod_mode_uses_default_prod_hosts(self) -> None:
        result = resolve_security_config(
            dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["prod.example"]
        )
        assert result.debug is True

    @patch.dict(
        os.environ,
        {
            "DJANGO_DEBUG": "False",
            "DJANGO_ALLOW_LAN": "False",
            "DJANGO_SECRET_KEY": "x" * 50,
            "CREDENTIAL_ENCRYPTION_KEY": _TEST_FAKE_FERNET_KEY,
        },
    )
    def test_production_defaults_and_debug_off(self) -> None:
        result = resolve_security_config(
            dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["localhost", "127.0.0.1"]
        )
        assert result.is_production is True
        assert result.debug is False
        assert "localhost" in result.allowed_hosts

    @patch.dict(os.environ, {"DJANGO_ALLOWED_HOSTS": "api.example.com,admin.example.com", "DJANGO_ALLOW_LAN": "False"})
    def test_env_allowed_hosts_overrides_defaults(self) -> None:
        result = resolve_security_config(
            dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["localhost"]
        )
        assert "api.example.com" in result.allowed_hosts
        assert "admin.example.com" in result.allowed_hosts
        assert "*" not in result.allowed_hosts

    @patch.dict(
        os.environ,
        {"DJANGO_ALLOW_LAN": "True", "DJANGO_LAN_ALLOWED_HOSTS": "192.168.31.230,localhost,127.0.0.1"},
    )
    def test_allow_lan_adds_lan_hosts_and_tailnet(self) -> None:
        result = resolve_security_config(
            dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["localhost"]
        )
        assert "*" not in result.allowed_hosts
        assert "192.168.31.230" in result.allowed_hosts
        assert "localhost" in result.allowed_hosts
        assert ".ts.net" in result.allowed_hosts

    @patch.dict(os.environ, {"DJANGO_ALLOW_LAN": "True", "DJANGO_LAN_ALLOWED_HOSTS": ""})
    def test_allow_lan_without_lan_hosts_raises(self) -> None:
        with pytest.raises(RuntimeError, match="DJANGO_LAN_ALLOWED_HOSTS"):
            resolve_security_config(
                dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["localhost"]
            )

    @patch.dict(os.environ, {"DJANGO_DEBUG": "False", "DJANGO_ALLOW_LAN": "True"})
    def test_allow_lan_in_production_raises(self) -> None:
        with pytest.raises(RuntimeError, match="生产环境"):
            resolve_security_config(
                dev_secret_key=_TEST_DEV_SECRET_KEY, default_allowed_hosts_dev=["*"], default_allowed_hosts_prod=["localhost"]
            )


class TestResolveContractFolderBrowseRoots:
    @patch.dict(os.environ, {"CONTRACT_FOLDER_BROWSE_ROOTS": "/home/user,/mnt/data"})
    def test_from_env(self) -> None:
        result = resolve_contract_folder_browse_roots()
        assert "/home/user" in result
        assert "/mnt/data" in result

    @patch.dict(os.environ, {"CONTRACT_FOLDER_BROWSE_ROOTS": ""})
    @patch("sys.platform", "darwin")
    def test_darwin_default(self) -> None:
        os.environ.pop("CONTRACT_FOLDER_BROWSE_ROOTS", None)
        result = resolve_contract_folder_browse_roots()
        assert "/Users" in result
