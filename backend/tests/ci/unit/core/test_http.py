"""测试 core.http 子模块

覆盖: httpx_clients.py, range.py
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# range.py - parse_range_header
# ============================================================


class TestParseRangeHeader:
    """测试 HTTP Range 解析"""

    def test_no_header(self) -> None:
        from apps.core.http.range import parse_range_header

        assert parse_range_header("", 1000) is None
        assert parse_range_header(None, 1000) is None  # type: ignore[arg-type]

    def test_wrong_prefix(self) -> None:
        from apps.core.http.range import parse_range_header

        assert parse_range_header("items=0-99", 1000) is None

    def test_explicit_range(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-499", 1000)
        assert result == (0, 499)

    def test_explicit_range_end_exceeds_filesize(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-9999", 1000)
        assert result == (0, 999)  # end 被限制在 file_size - 1

    def test_suffix_range(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=-500", 1000)
        assert result == (500, 999)

    def test_suffix_range_larger_than_file(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=-2000", 1000)
        assert result == (0, 999)

    def test_open_ended_range(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=100-", 1000)
        assert result == (100, 999)

    def test_multiple_ranges_takes_first(self) -> None:
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-99, 200-299", 1000)
        assert result == (0, 99)

    def test_negative_start_returns_none(self) -> None:
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=-5-100", 1000) is None

    def test_end_less_than_start(self) -> None:
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=500-100", 1000) is None

    def test_zero_suffix(self) -> None:
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=-0", 1000) is None


# ============================================================
# httpx_clients.py
# ============================================================


class TestHttpxClients:
    """测试 httpx 客户端工厂函数"""

    @patch.dict("os.environ", {"DJANGO_HTTPX_METRICS": "false"})
    def test_get_sync_http_client(self) -> None:
        from apps.core.http.httpx_clients import get_sync_http_client

        # 清除缓存
        get_sync_http_client.cache_clear()
        client = get_sync_http_client()
        assert client is not None
        get_sync_http_client.cache_clear()

    @patch.dict("os.environ", {"DJANGO_HTTPX_METRICS": "false"})
    def test_get_async_http_client(self) -> None:
        from apps.core.http.httpx_clients import get_async_http_client

        get_async_http_client.cache_clear()
        client = get_async_http_client()
        assert client is not None
        get_async_http_client.cache_clear()

    @patch.dict("os.environ", {"DJANGO_HTTPX_METRICS": "true"})
    def test_event_hooks_enabled(self) -> None:
        from apps.core.http.httpx_clients import _httpx_event_hooks

        hooks = _httpx_event_hooks()
        assert hooks is not None
        assert "request" in hooks
        assert "response" in hooks

    @patch.dict("os.environ", {"DJANGO_HTTPX_METRICS": "false"})
    def test_event_hooks_disabled(self) -> None:
        from apps.core.http.httpx_clients import _httpx_event_hooks

        hooks = _httpx_event_hooks()
        assert hooks is None

    @patch.dict("os.environ", {"DJANGO_HTTPX_METRICS": "false"})
    def test_client_has_timeout(self) -> None:
        from apps.core.http.httpx_clients import get_sync_http_client

        get_sync_http_client.cache_clear()
        client = get_sync_http_client()
        assert client.timeout.connect == 60.0
        get_sync_http_client.cache_clear()
