"""Tests for apps.core.middleware.token_rate_limit."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware


class TestTokenRateLimitMiddleware:
    def _make_request(self, path="/api/v1/token/", method="POST", ip="127.0.0.1"):
        request = MagicMock()
        request.path = path
        request.method = method
        request.META = {"REMOTE_ADDR": ip, "HTTP_X_FORWARDED_FOR": ""}
        return request

    def test_non_token_path_passes_through(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request(path="/api/v1/users/")
        result = middleware(request)
        assert result == "ok"

    def test_get_request_passes_through(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request(method="GET")
        result = middleware(request)
        assert result == "ok"

    def test_first_request_passes(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = middleware(request)
            assert result == "ok"

    def test_rate_limited(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = 11  # Over limit
            result = middleware(request)
            assert result.status_code == 429

    def test_increment_existing_count(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = 5
            result = middleware(request)
            assert result == "ok"
            mock_cache.set.assert_called()

    def test_cache_exception_passes_through(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.side_effect = Exception("cache down")
            result = middleware(request)
            assert result == "ok"

    def test_xff_ip(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 10.0.0.2"
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = middleware(request)
            assert result == "ok"

    def test_no_xff_uses_remote_addr(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request(ip="192.168.1.1")
        request.META["HTTP_X_FORWARDED_FOR"] = ""
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = middleware(request)
            assert result == "ok"
