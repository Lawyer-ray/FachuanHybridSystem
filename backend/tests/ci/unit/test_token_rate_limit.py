"""Tests for apps.core.middleware.token_rate_limit."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

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
            mock_cache.add.return_value = True  # First request, key created
            result = middleware(request)
            assert result == "ok"

    def test_rate_limited(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.add.return_value = False  # Key already exists
            mock_cache.incr.return_value = 12  # Over limit
            result = middleware(request)
            assert result.status_code == 429
            # 429 响应应携带限流错误码与中文提示
            import json

            data = json.loads(result.content)
            assert data["code"] == "RATE_LIMITED"
            assert data["detail"] == "请求过于频繁，请稍后重试"
            # 触发限流后不应再调用下游视图
            get_response.assert_not_called()

    def test_increment_existing_count(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.add.return_value = False  # Key already exists
            mock_cache.incr.return_value = 5
            result = middleware(request)
            assert result == "ok"
            mock_cache.incr.assert_called()

    def test_cache_exception_passes_through(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.add.side_effect = Exception("cache down")
            result = middleware(request)
            assert result == "ok"

    def test_xff_ip(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request()
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 10.0.0.2"
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.add.return_value = True
            result = middleware(request)
            assert result == "ok"

    def test_no_xff_uses_remote_addr(self):
        get_response = MagicMock(return_value="ok")
        middleware = TokenRateLimitMiddleware(get_response)
        request = self._make_request(ip="192.168.1.1")
        request.META["HTTP_X_FORWARDED_FOR"] = ""
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.add.return_value = True
            result = middleware(request)
            assert result == "ok"


class TestAsyncCheckRate:
    """异步链路计数应使用 aadd + aincr 原子语义（回归：aget+aset 并发丢计数）。"""

    @pytest.mark.asyncio
    async def test_first_request_uses_aadd(self):
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.aadd = AsyncMock(return_value=True)
            mock_cache.aincr = AsyncMock()
            count = await TokenRateLimitMiddleware._async_check_rate("bucket")
            assert count == 1
            mock_cache.aadd.assert_awaited_once()
            mock_cache.aincr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_key_increments_atomically(self):
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.aadd = AsyncMock(return_value=False)
            mock_cache.aincr = AsyncMock(return_value=4)
            count = await TokenRateLimitMiddleware._async_check_rate("bucket")
            assert count == 4
            mock_cache.aincr.assert_awaited_once_with("bucket")
            mock_cache.aset.assert_not_called()

    @pytest.mark.asyncio
    async def test_incr_value_error_falls_back_to_aset(self):
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.aadd = AsyncMock(return_value=False)
            mock_cache.aincr = AsyncMock(side_effect=ValueError("key not found"))
            mock_cache.aset = AsyncMock()
            count = await TokenRateLimitMiddleware._async_check_rate("bucket")
            assert count == 1
            mock_cache.aset.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_exception_fails_open(self):
        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.aadd = AsyncMock(side_effect=Exception("cache down"))
            count = await TokenRateLimitMiddleware._async_check_rate("bucket")
            assert count == 0  # 缓存故障时放行
