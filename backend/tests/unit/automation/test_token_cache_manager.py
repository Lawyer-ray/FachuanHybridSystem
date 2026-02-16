from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.automation.services.token.cache_manager import TokenCacheManager
from apps.core.dtos import AccountCredentialDTO
from apps.core.telemetry.metrics import snapshot


def test_token_cache_key_does_not_contain_plain_account():
    manager = TokenCacheManager()
    account = "user@example.com"
    key = manager._get_token_cache_key("site", account)
    assert account not in key
    assert "@" not in key


def test_token_cache_key_sanitizes_site_name():
    manager = TokenCacheManager()
    key = manager._get_token_cache_key("Court ZXFW / 2026", "user@example.com")
    assert " " not in key
    assert "/" not in key
    assert "Court ZXFW / 2026" not in key


def test_clear_all_cache_refuses_in_production_without_explicit_allow(settings, monkeypatch):
    settings.DEBUG = False
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "t1"}}
    monkeypatch.delenv("ALLOW_CACHE_CLEAR", raising=False)

    cache.clear()
    manager = TokenCacheManager()
    manager.cache_token("site", "user@example.com", "t1")
    manager.clear_all_cache()
    assert manager.get_cached_token("site", "user@example.com") == "t1"


def test_clear_all_cache_removes_cached_token(settings):
    settings.DEBUG = True
    cache.clear()
    manager = TokenCacheManager()
    manager.cache_token("site", "user@example.com", "t1")
    assert manager.get_cached_token("site", "user@example.com") == "t1"
    manager.clear_all_cache()
    assert manager.get_cached_token("site", "user@example.com") is None


def test_clear_all_cache_redis_backend_refuses_without_explicit_allow(settings, monkeypatch):
    settings.DEBUG = False
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://x"}}
    monkeypatch.delenv("ALLOW_CACHE_CLEAR", raising=False)

    called = {"n": 0}

    def fake_clear_redis(*args, **kwargs):
        called["n"] += 1

    monkeypatch.setattr(TokenCacheManager, "_clear_redis_namespace_cache", fake_clear_redis)
    TokenCacheManager().clear_all_cache()
    assert called["n"] == 0


def test_clear_redis_namespace_cache_gracefully_handles_missing_redis_dependency(monkeypatch):
    import builtins

    import apps.automation.services.token.cache_manager as mod

    manager = TokenCacheManager()
    called = {"msg": None}

    def fake_warning(msg, *args, **kwargs):
        called["msg"] = msg

    monkeypatch.setattr(mod.logger, "warning", fake_warning)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis":
            raise ModuleNotFoundError("No module named 'redis'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    manager._clear_redis_namespace_cache({"LOCATION": "redis://x"}, backend="django.core.cache.backends.redis.RedisCache")
    assert called["msg"] == "token_cache_clear_redis_client_init_failed"


def test_clear_redis_namespace_cache_warns_when_location_missing(monkeypatch):
    import apps.automation.services.token.cache_manager as mod

    manager = TokenCacheManager()
    called = {"msg": None}

    def fake_warning(msg, *args, **kwargs):
        called["msg"] = msg

    monkeypatch.setattr(mod.logger, "warning", fake_warning)
    manager._clear_redis_namespace_cache({}, backend="django.core.cache.backends.redis.RedisCache")
    assert called["msg"] == "token_cache_clear_redis_location_missing"


def test_cache_token_skips_when_expiring_soon():
    cache.clear()
    manager = TokenCacheManager()
    cache_key = manager._get_token_cache_key("site", "user@example.com")
    manager.cache_token("site", "user@example.com", "t1", expires_at=timezone.now() + timedelta(minutes=4))
    assert cache.get(cache_key) is None


def test_token_cache_access_is_exposed_in_resource_metrics_snapshot():
    cache.clear()
    manager = TokenCacheManager()
    assert manager.get_cached_token("site", "user@example.com") is None
    data = snapshot(window_minutes=1)
    token_cache = data.get("automation_token_cache") or {}
    assert int(token_cache.get("total") or 0) >= 1
    by_name = token_cache.get("by_name") or []
    entry = next((e for e in by_name if e.get("name") == "token"), None)
    assert entry is not None
    assert int(entry.get("misses") or 0) >= 1


def test_cache_credentials_does_not_store_password():
    cache.clear()
    manager = TokenCacheManager()
    site_name = "court_zxfw"
    secret = "super_secret_password"
    credential = AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        site_name=site_name,
        url="https://zxfw.court.gov.cn",
        account="test_user",
        password=secret,
        last_login_success_at=timezone.now().isoformat(),
        login_success_count=1,
        login_failure_count=0,
        is_preferred=True,
        created_at=timezone.now().isoformat(),
        updated_at=timezone.now().isoformat(),
    )

    manager.cache_credentials(site_name, [credential])
    cache_key = manager._get_credentials_cache_key(site_name)
    raw = cache.get(cache_key)
    assert raw is not None
    assert isinstance(raw, list)
    assert raw[0].get("password") == ""
    assert secret not in str(raw[0])

    restored = manager.get_cached_credentials(site_name)
    assert restored is not None
    assert restored[0].password == ""
