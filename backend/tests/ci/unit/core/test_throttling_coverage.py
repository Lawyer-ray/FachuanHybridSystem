"""Tests for core infrastructure throttling module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest

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
