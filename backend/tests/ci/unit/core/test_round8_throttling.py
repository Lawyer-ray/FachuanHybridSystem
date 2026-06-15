"""Tests for throttling, dashboard_service, case_command_service helpers, and task_lifecycle."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import MagicMock, patch

import pytest

from apps.core.infrastructure.throttling import (
    RateLimiter,
    get_rate_limit_config,
)
from apps.core.exceptions import RateLimitError


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_init_defaults(self):
        rl = RateLimiter()
        assert rl.requests == 100
        assert rl.window == 60
        assert rl.key_prefix == "ratelimit"

    def test_init_custom(self):
        rl = RateLimiter(requests=10, window=30, key_prefix="test")
        assert rl.requests == 10
        assert rl.window == 30
        assert rl.key_prefix == "test"

    def test_get_client_ip_remote_addr(self):
        rl = RateLimiter()
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        assert rl.get_client_ip(request) == "192.168.1.1"

    def test_get_client_ip_unknown(self):
        rl = RateLimiter()
        request = MagicMock()
        request.META = {}
        assert rl.get_client_ip(request) == "unknown"

    def test_get_client_ip_xff_no_trust(self):
        rl = RateLimiter()
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8", "REMOTE_ADDR": "10.0.0.1"}
        with patch.dict("os.environ", {}, clear=False):
            # Without trust, xff is ignored, returns REMOTE_ADDR
            assert rl.get_client_ip(request) == "10.0.0.1"

    def test_get_cache_key_default(self):
        rl = RateLimiter()
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        request.path = "/api/test"
        key = rl.get_cache_key(request)
        assert key.startswith("ratelimit:")
        expected_hash = hashlib.md5(b"10.0.0.1:/api/test", usedforsecurity=False).hexdigest()[:16]
        assert key == f"ratelimit:{expected_hash}"

    def test_get_cache_key_custom_func(self):
        rl = RateLimiter()
        request = MagicMock()
        key = rl.get_cache_key(request, key_func=lambda r: "custom_key")
        expected_hash = hashlib.md5(b"custom_key", usedforsecurity=False).hexdigest()[:16]
        assert key == f"ratelimit:{expected_hash}"

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_under_limit(self, mock_cache):
        mock_cache.add.return_value = True
        rl = RateLimiter(requests=10, window=60)
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        request.path = "/api/test"
        allowed, info = rl.is_allowed(request)
        assert allowed is True
        assert info["limit"] == 10
        assert info["remaining"] >= 0

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_over_limit(self, mock_cache):
        mock_cache.add.return_value = False
        mock_cache.incr.return_value = 11
        rl = RateLimiter(requests=10, window=60)
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        request.path = "/api/test"
        allowed, info = rl.is_allowed(request)
        assert allowed is False

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_incr_value_error(self, mock_cache):
        mock_cache.add.return_value = False
        mock_cache.incr.side_effect = ValueError
        rl = RateLimiter(requests=10, window=60)
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        request.path = "/api/test"
        allowed, info = rl.is_allowed(request)
        # After incr fails, cache.set is called, count becomes 1, so allowed
        assert allowed is True


# ---------------------------------------------------------------------------
# get_rate_limit_config
# ---------------------------------------------------------------------------


class TestGetRateLimitConfig:
    def test_with_settings(self):
        with patch("django.conf.settings") as mock_settings:
            mock_settings.RATE_LIMIT = {
                "DEFAULT_REQUESTS": 200,
                "DEFAULT_WINDOW": 120,
            }
            req, win = get_rate_limit_config("test", fallback_requests=10, fallback_window=30)
            assert req == 200
            assert win == 120

    def test_kind_specific(self):
        with patch("django.conf.settings") as mock_settings:
            mock_settings.RATE_LIMIT = {
                "DEFAULT_REQUESTS": 200,
                "DEFAULT_WINDOW": 120,
                "auth_REQUESTS": 5,
                "auth_WINDOW": 30,
            }
            req, win = get_rate_limit_config("auth", fallback_requests=10, fallback_window=30)
            assert req == 5
            assert win == 30

    def test_no_settings_fallback(self):
        with patch("django.conf.settings", new_callable=lambda: type("S", (), {"__getattr__": lambda s, n: (_ for _ in ()).throw(ImportError)})):
            req, win = get_rate_limit_config("test", fallback_requests=10, fallback_window=30)
            assert req == 10
            assert win == 30


# ---------------------------------------------------------------------------
# rate_limit decorator
# ---------------------------------------------------------------------------


class TestRateLimitDecorator:
    def test_sync_allowed(self):
        from apps.core.infrastructure.throttling import rate_limit

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (True, {"limit": 10, "remaining": 9, "reset": 100, "window": 60})
        request = MagicMock()

        @rate_limit(requests=10, window=60, limiter=mock_limiter)
        def my_view(request: MagicMock) -> str:
            return "ok"

        result = my_view(request)
        assert result == "ok"

    def test_sync_blocked(self):
        from apps.core.infrastructure.throttling import rate_limit

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (False, {"limit": 10, "remaining": 0, "reset": 100, "window": 60})
        request = MagicMock()

        @rate_limit(requests=10, window=60, limiter=mock_limiter)
        def my_view(request: MagicMock) -> str:
            return "ok"

        with pytest.raises(RateLimitError):
            my_view(request)

    @pytest.mark.asyncio
    async def test_async_allowed(self):
        import asyncio
        from apps.core.infrastructure.throttling import rate_limit

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (True, {"limit": 10, "remaining": 9, "reset": 100, "window": 60})
        request = MagicMock()

        @rate_limit(requests=10, window=60, limiter=mock_limiter)
        async def my_view(request: MagicMock) -> str:
            return "ok"

        result = asyncio.get_event_loop().run_until_complete(my_view(request))
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_blocked(self):
        import asyncio
        from apps.core.infrastructure.throttling import rate_limit

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (False, {"limit": 10, "remaining": 0, "reset": 100, "window": 60})
        request = MagicMock()

        @rate_limit(requests=10, window=60, limiter=mock_limiter)
        async def my_view(request: MagicMock) -> str:
            return "ok"

        with pytest.raises(RateLimitError):
            asyncio.get_event_loop().run_until_complete(my_view(request))
