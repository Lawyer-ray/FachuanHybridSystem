"""Tests for core infrastructure throttling module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest
from django.test import override_settings

from apps.core.exceptions import RateLimitError
from apps.core.infrastructure.throttling import (
    RateLimiter,
    auth_limiter,
    default_limiter,
    get_rate_limit_config,
    rate_limit,
    rate_limit_by_user,
    rate_limit_from_settings,
    strict_limiter,
)


class TestRateLimiter:
    def setup_method(self) -> None:
        self.limiter = RateLimiter(requests=5, window=60, key_prefix="test")

    def test_init(self) -> None:
        assert self.limiter.requests == 5
        assert self.limiter.window == 60
        assert self.limiter.key_prefix == "test"

    def test_get_client_ip_remote_addr(self) -> None:
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        assert self.limiter.get_client_ip(request) == "192.168.1.1"

    def test_get_client_ip_unknown(self) -> None:
        request = MagicMock(spec=HttpRequest)
        request.META = {}
        assert self.limiter.get_client_ip(request) == "unknown"

    def test_get_client_ip_forwarded_for(self) -> None:
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2",
            "REMOTE_ADDR": "192.168.1.1",
        }
        with patch.dict("os.environ", {"DJANGO_TRUST_X_FORWARDED_FOR": "true"}):
            result = self.limiter.get_client_ip(request)
        assert result in ("10.0.0.1", "192.168.1.1")

    def test_client_ip_header_default_none_unchanged(self) -> None:
        """未配置 DJANGO_CLIENT_IP_HEADER 时行为不变（回退 REMOTE_ADDR）。"""
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_CF_CONNECTING_IP": "203.0.113.9",
        }
        with (
            override_settings(DJANGO_CLIENT_IP_HEADER=None),
            patch.dict("os.environ", {"DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"}),
        ):
            assert self.limiter.get_client_ip(request) == "127.0.0.1"

    def test_client_ip_header_used_when_trusted_proxy(self) -> None:
        """配置了专用头且直连对端是受信代理时，直接采用该头（CF Tunnel 场景）。"""
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_CF_CONNECTING_IP": "203.0.113.9",
        }
        with (
            override_settings(DJANGO_CLIENT_IP_HEADER="CF-Connecting-IP"),
            patch.dict("os.environ", {"DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"}),
        ):
            assert self.limiter.get_client_ip(request) == "203.0.113.9"

    def test_client_ip_header_meta_key_style_supported(self) -> None:
        """META 键形式（HTTP_CF_CONNECTING_IP）与 HTTP 头名形式等价。"""
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_CF_CONNECTING_IP": "198.51.100.7",
        }
        with (
            override_settings(DJANGO_CLIENT_IP_HEADER="HTTP_CF_CONNECTING_IP"),
            patch.dict("os.environ", {"DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"}),
        ):
            assert self.limiter.get_client_ip(request) == "198.51.100.7"

    def test_client_ip_header_ignored_when_proxy_untrusted(self) -> None:
        """直连对端不属于受信代理时忽略该头（防伪造，回退 REMOTE_ADDR）。"""
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "REMOTE_ADDR": "203.0.113.50",
            "HTTP_CF_CONNECTING_IP": "203.0.113.9",
        }
        with (
            override_settings(DJANGO_CLIENT_IP_HEADER="CF-Connecting-IP"),
            patch.dict("os.environ", {"DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"}),
        ):
            assert self.limiter.get_client_ip(request) == "203.0.113.50"

    def test_client_ip_header_empty_falls_back(self) -> None:
        """头存在但为空时回退原有链路。"""
        request = MagicMock(spec=HttpRequest)
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_CF_CONNECTING_IP": "  ",
        }
        with (
            override_settings(DJANGO_CLIENT_IP_HEADER="CF-Connecting-IP"),
            patch.dict("os.environ", {"DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"}),
        ):
            assert self.limiter.get_client_ip(request) == "127.0.0.1"

    def test_get_cache_key_default(self) -> None:
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        key = self.limiter.get_cache_key(request)
        assert key.startswith("test:")
        assert len(key) > 5

    def test_get_cache_key_custom_func(self) -> None:
        request = MagicMock(spec=HttpRequest)

        def custom_func(r):
            return "custom_key"

        key = self.limiter.get_cache_key(request, key_func=custom_func)
        assert "test:" in key

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_first_request(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = True
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        allowed, info = self.limiter.is_allowed(request)
        assert allowed is True
        assert info["limit"] == 5
        assert info["remaining"] == 4

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_exceeded(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = False
        mock_cache.incr.return_value = 10  # over limit
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        allowed, info = self.limiter.is_allowed(request)
        assert allowed is False
        assert info["remaining"] == 0

    @patch("apps.core.infrastructure.throttling.cache")
    def test_is_allowed_incr_value_error(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = False
        mock_cache.incr.side_effect = ValueError("key not found")
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        allowed, info = self.limiter.is_allowed(request)
        assert allowed is True
        mock_cache.set.assert_called()


class TestPredefinedLimiters:
    def test_default_limiter(self) -> None:
        assert default_limiter.requests == 100
        assert default_limiter.window == 60

    def test_strict_limiter(self) -> None:
        assert strict_limiter.requests == 10

    def test_auth_limiter(self) -> None:
        assert auth_limiter.requests == 5


class TestGetRateLimitConfig:
    def test_default_fallback(self) -> None:
        requests, window = get_rate_limit_config("EXPORT", fallback_requests=20, fallback_window=60)
        assert requests >= 20  # May use settings value if available
        assert window >= 60

    def test_returns_tuple(self) -> None:
        requests, window = get_rate_limit_config("AUTH", fallback_requests=5, fallback_window=60)
        assert isinstance(requests, int)
        assert isinstance(window, int)


class TestRateLimitDecorator:
    @patch("apps.core.infrastructure.throttling.cache")
    def test_allows_request(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = True

        @rate_limit(requests=10, window=60)
        def my_view(request: HttpRequest) -> dict:
            return {"ok": True}

        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        result = my_view(request)
        assert result == {"ok": True}

    @patch("apps.core.infrastructure.throttling.cache")
    def test_blocks_request(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = False
        mock_cache.incr.return_value = 100

        @rate_limit(requests=5, window=60)
        def my_view(request: HttpRequest) -> dict:
            return {"ok": True}

        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        with pytest.raises(RateLimitError):
            my_view(request)

    @patch("apps.core.infrastructure.throttling.cache")
    def test_preserves_function_name(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = True

        @rate_limit(requests=10, window=60)
        def my_view(request: HttpRequest) -> dict:
            return {"ok": True}

        assert my_view.__name__ == "my_view"


class TestRateLimitByUser:
    @patch("apps.core.infrastructure.throttling.cache")
    def test_authenticated_user(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = True

        @rate_limit_by_user(requests=10, window=60)
        def my_view(request: HttpRequest) -> dict:
            return {"ok": True}

        request = MagicMock(spec=HttpRequest)
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.id = 42
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        result = my_view(request)
        assert result == {"ok": True}

    @patch("apps.core.infrastructure.throttling.cache")
    def test_anonymous_user(self, mock_cache: MagicMock) -> None:
        mock_cache.add.return_value = True

        @rate_limit_by_user(requests=10, window=60)
        def my_view(request: HttpRequest) -> dict:
            return {"ok": True}

        request = MagicMock(spec=HttpRequest)
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        result = my_view(request)
        assert result == {"ok": True}


class TestAsyncRateLimit:
    """异步限流路径：async 端点走 ais_allowed（aadd/aincr），不再阻塞事件循环。"""

    @staticmethod
    def _make_request() -> MagicMock:
        request = MagicMock(spec=HttpRequest)
        request.META = {"REMOTE_ADDR": "1.2.3.4"}
        request.path = "/api/test"
        return request

    @patch("apps.core.infrastructure.throttling.cache")
    def test_async_wrapper_awaits_ais_allowed(self, mock_cache: MagicMock) -> None:
        from unittest.mock import AsyncMock

        from asgiref.sync import async_to_sync

        mock_cache.aadd = AsyncMock(return_value=True)

        @rate_limit(requests=10, window=60)
        async def my_async_view(request: HttpRequest) -> dict:
            return {"ok": True}

        result = async_to_sync(my_async_view)(self._make_request())
        assert result == {"ok": True}
        mock_cache.aadd.assert_awaited_once()
        mock_cache.add.assert_not_called()  # 同步计数路径不应被触碰

    @patch("apps.core.infrastructure.throttling.cache")
    def test_async_wrapper_blocks_over_limit(self, mock_cache: MagicMock) -> None:
        from unittest.mock import AsyncMock

        from asgiref.sync import async_to_sync

        mock_cache.aadd = AsyncMock(return_value=False)
        mock_cache.aincr = AsyncMock(return_value=11)

        @rate_limit(requests=10, window=60)
        async def my_async_view(request: HttpRequest) -> dict:
            return {"ok": True}

        with pytest.raises(RateLimitError):
            async_to_sync(my_async_view)(self._make_request())

    @patch("apps.core.infrastructure.throttling.cache")
    def test_ais_allowed_incr_recovery_on_value_error(self, mock_cache: MagicMock) -> None:
        from unittest.mock import AsyncMock

        from asgiref.sync import async_to_sync

        mock_cache.aadd = AsyncMock(return_value=False)
        mock_cache.aincr = AsyncMock(side_effect=ValueError("expired"))
        mock_cache.aset = AsyncMock(return_value=True)

        limiter = RateLimiter(requests=5, window=60)
        allowed, info = async_to_sync(limiter.ais_allowed)(self._make_request())
        assert allowed is True
        assert info["remaining"] == 4
        mock_cache.aset.assert_awaited_once()
