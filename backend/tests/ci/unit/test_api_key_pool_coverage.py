"""Unit tests for McpApiKeyPool."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool


def _pool(*keys: str, provider: str = "test") -> McpApiKeyPool:
    return McpApiKeyPool(provider_name=provider, api_keys=list(keys))


# ── __init__ ──────────────────────────────────────────────────────────────────

def test_init_deduplicates_keys() -> None:
    pool = _pool("key1", "key1", "key2")
    assert pool.size == 2


def test_init_filters_empty_values() -> None:
    pool = _pool("key1", "", "  ", "key2")
    assert pool.size == 2


def test_init_empty_keys() -> None:
    pool = _pool()
    assert pool.size == 0


# ── ordered_keys ──────────────────────────────────────────────────────────────

def test_ordered_keys_single_key() -> None:
    pool = _pool("key1")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        mock_cache.get.return_value = None
        result = pool.ordered_keys()
    assert result == ["key1"]


def test_ordered_keys_multiple_keys_no_preferred() -> None:
    pool = _pool("key1", "key2", "key3")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        mock_cache.get.return_value = None
        result = pool.ordered_keys()
    assert set(result) == {"key1", "key2", "key3"}
    assert len(result) == 3


def test_ordered_keys_preferred_key_comes_first() -> None:
    pool = _pool("key1", "key2", "key3")
    preferred_fp = pool.fingerprint("key2")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        mock_cache.get.return_value = preferred_fp
        result = pool.ordered_keys()
    assert result[0] == "key2"


def test_ordered_keys_blocked_key_goes_last() -> None:
    pool = _pool("key1", "key2")
    blocked_fp = pool.fingerprint("key1")

    def cache_get(key: str) -> object:
        if "blocked" in key and blocked_fp in key:
            return True
        return None

    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        mock_cache.get.side_effect = cache_get
        result = pool.ordered_keys()

    assert result[-1] == "key1"
    assert result[0] == "key2"


# ── mark_success ──────────────────────────────────────────────────────────────

def test_mark_success_sets_preferred_and_clears_block() -> None:
    pool = _pool("key1", "key2")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        pool.mark_success("key1")
    mock_cache.set.assert_called_once()
    mock_cache.delete.assert_called_once()


def test_mark_success_empty_key_does_nothing() -> None:
    pool = _pool("key1")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        pool.mark_success("")
    mock_cache.set.assert_not_called()


# ── mark_auth_failed / mark_rate_limited ─────────────────────────────────────

def test_mark_auth_failed_sets_block() -> None:
    pool = _pool("key1")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        pool.mark_auth_failed("key1")
    mock_cache.set.assert_called_once()
    args = mock_cache.set.call_args
    # auth block TTL is 1 hour = 3600s
    assert args[1]["timeout"] == 3600


def test_mark_rate_limited_sets_block_with_short_ttl() -> None:
    pool = _pool("key1")
    with patch("apps.enterprise_data.services.clients.api_key_pool.cache") as mock_cache:
        pool.mark_rate_limited("key1")
    mock_cache.set.assert_called_once()
    args = mock_cache.set.call_args
    # rate limit block TTL is 2 minutes = 120s
    assert args[1]["timeout"] == 120


# ── fingerprint ───────────────────────────────────────────────────────────────

def test_fingerprint_returns_16_char_hex() -> None:
    pool = _pool("key1")
    fp = pool.fingerprint("key1")
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_empty_returns_empty_string() -> None:
    pool = _pool()
    assert pool.fingerprint("") == ""
    assert pool.fingerprint("  ") == ""


def test_fingerprint_same_key_same_result() -> None:
    pool = _pool("key1")
    assert pool.fingerprint("key1") == pool.fingerprint("key1")


def test_fingerprint_different_keys_different_results() -> None:
    pool = _pool("key1", "key2")
    assert pool.fingerprint("key1") != pool.fingerprint("key2")
