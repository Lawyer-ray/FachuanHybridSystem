import pytest
from django.core.cache import cache

from apps.core.exceptions import RateLimitError
from apps.core.infrastructure.throttling import (
    RateLimiter,
    get_rate_limit_config,
    rate_limit,
    rate_limit_by_user,
    rate_limit_from_settings,
)


class DummyRequest:
    def __init__(self, *, path: str = "/x", ip: str = "127.0.0.1", xff: str | None = None):
        self.path = path
        self.META = {"REMOTE_ADDR": ip}
        if xff is not None:
            self.META["HTTP_X_FORWARDED_FOR"] = xff
        self.headers: dict[str, str] = {}


@pytest.mark.unit
def test_rate_limit_sync_raises_429_on_overflow():
    cache.clear()
    request = DummyRequest(path="/sync")

    @rate_limit(requests=1, window=60)
    def handler(_request):
        return {"ok": True}

    assert handler(request) == {"ok": True}
    with pytest.raises(RateLimitError) as exc:
        handler(request)
    assert exc.value.code == "RATE_LIMIT_ERROR"
    assert "retry_after" in (exc.value.errors or {})


@pytest.mark.anyio
@pytest.mark.unit
async def test_rate_limit_async_raises_429_on_overflow():
    cache.clear()
    request = DummyRequest(path="/async")

    @rate_limit(requests=1, window=60)
    async def handler(_request):
        return {"ok": True}

    assert await handler(request) == {"ok": True}
    with pytest.raises(RateLimitError) as exc:
        await handler(request)
    assert exc.value.code == "RATE_LIMIT_ERROR"
    assert "retry_after" in (exc.value.errors or {})


@pytest.mark.unit
def test_get_client_ip_prefers_remote_addr_by_default():
    request = DummyRequest(ip="10.0.0.9")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "10.0.0.9"


@pytest.mark.unit
def test_get_client_ip_does_not_trust_xff_without_trusted_proxy_in_production(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.delenv("DJANGO_TRUSTED_PROXY_IPS", raising=False)
    request = DummyRequest(ip="10.0.0.9", xff="1.1.1.1, 2.2.2.2")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "10.0.0.9"


@pytest.mark.unit
def test_get_client_ip_uses_xff_when_remote_addr_is_trusted_proxy(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_TRUSTED_PROXY_IPS", "10.0.0.9")
    request = DummyRequest(ip="10.0.0.9", xff="1.1.1.1, 2.2.2.2")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "1.1.1.1"


@pytest.mark.unit
def test_get_client_ip_supports_trusted_proxy_hops(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_TRUSTED_PROXY_IPS", "10.0.0.9")
    monkeypatch.setenv("DJANGO_TRUSTED_PROXY_HOPS", "1")
    request = DummyRequest(ip="10.0.0.9", xff="1.1.1.1, 2.2.2.2")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "1.1.1.1"


@pytest.mark.unit
def test_get_client_ip_allows_unverified_xff_in_debug(settings, monkeypatch):
    settings.DEBUG = True
    monkeypatch.setenv("DJANGO_TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.delenv("DJANGO_TRUSTED_PROXY_IPS", raising=False)
    request = DummyRequest(ip="10.0.0.9", xff="1.1.1.1, 2.2.2.2")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "1.1.1.1"


@pytest.mark.unit
def test_get_client_ip_ignores_invalid_trusted_hops(monkeypatch):
    monkeypatch.setenv("DJANGO_TRUSTED_PROXY_IPS", "10.0.0.9")
    monkeypatch.setenv("DJANGO_TRUSTED_PROXY_HOPS", "not-an-int")
    request = DummyRequest(ip="10.0.0.9", xff="1.1.1.1, 2.2.2.2")
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "1.1.1.1"


@pytest.mark.unit
def test_get_client_ip_returns_unknown_when_no_meta(monkeypatch):
    monkeypatch.setenv("DJANGO_TRUST_X_FORWARDED_FOR", "true")

    request = DummyRequest(ip="")
    request.META = {}
    ip = RateLimiter().get_client_ip(request)  # type: ignore[arg-type]
    assert ip == "unknown"


@pytest.mark.unit
def test_rate_limiter_recovers_from_cache_incr_value_error(monkeypatch):
    limiter = RateLimiter(requests=1, window=60)
    request = DummyRequest(path="/v")

    def add(_key, _value, timeout=None):
        return False

    def incr(_key):
        raise ValueError("bad cache value")

    calls: list[tuple[str, int | None]] = []

    def set_value(key, value, timeout=None):
        calls.append((key, timeout))

    monkeypatch.setattr(cache, "add", add)
    monkeypatch.setattr(cache, "incr", incr)
    monkeypatch.setattr(cache, "set", set_value)

    allowed, info = limiter.is_allowed(request)  # type: ignore[arg-type]
    assert allowed is True
    assert info["remaining"] in (0, 1)
    assert calls


@pytest.mark.unit
def test_get_rate_limit_config_reads_settings(settings):
    settings.RATE_LIMIT = {
        "DEFAULT_REQUESTS": 9,
        "DEFAULT_WINDOW": 7,
        "AUTH_REQUESTS": 3,
        "AUTH_WINDOW": 5,
    }
    requests, window = get_rate_limit_config("AUTH", fallback_requests=100, fallback_window=60)
    assert (requests, window) == (3, 5)
    requests, window = get_rate_limit_config("MISSING", fallback_requests=100, fallback_window=60)
    assert (requests, window) == (9, 7)


@pytest.mark.unit
def test_rate_limit_by_user_uses_user_or_ip_branches(monkeypatch):
    cache.clear()
    request_user = DummyRequest(path="/by-user", ip="10.0.0.1")
    request_user.user = type("U", (), {"is_authenticated": True, "id": 123})()  # type: ignore[attr-defined]

    @rate_limit_by_user(requests=1, window=60)
    def handler(_request):
        return {"ok": True}

    assert handler(request_user) == {"ok": True}
    with pytest.raises(RateLimitError):
        handler(request_user)

    cache.clear()
    request_anon = DummyRequest(path="/by-user", ip="10.0.0.2")
    request_anon.user = type("U", (), {"is_authenticated": False, "id": 999})()  # type: ignore[attr-defined]
    assert handler(request_anon) == {"ok": True}
    with pytest.raises(RateLimitError):
        handler(request_anon)


@pytest.mark.unit
def test_rate_limit_from_settings_applies_kind_specific_limits(settings):
    cache.clear()
    settings.RATE_LIMIT = {
        "DEFAULT_REQUESTS": 10,
        "DEFAULT_WINDOW": 60,
        "LOGIN_REQUESTS": 1,
        "LOGIN_WINDOW": 60,
    }
    request = DummyRequest(path="/from-settings", ip="10.0.0.3")

    @rate_limit_from_settings("LOGIN", by_user=False)
    def handler(_request):
        return {"ok": True}

    assert handler(request) == {"ok": True}
    with pytest.raises(RateLimitError):
        handler(request)
