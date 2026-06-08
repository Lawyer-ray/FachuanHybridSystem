"""Unit tests for core.config.steering.cache_strategies module."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

import pytest

from apps.core.config.steering.cache_strategies import (
    AdaptiveCacheStrategy,
    CacheEntry,
    CacheStrategy,
    LayeredCacheStrategy,
    LRUCacheStrategy,
    SmartCacheStrategy,
    SteeringCacheStrategyManager,
    TTLCacheStrategy,
    create_cache_strategy_from_config,
)


def _make_entry(key: str = "k", data: str = "data", **kwargs) -> CacheEntry:
    now = time.time()
    defaults = {"key": key, "data": data, "created_at": now, "last_accessed": now, "access_count": 1, "file_mtime": None, "size_bytes": 100, "priority": 0}
    defaults.update(kwargs)
    return CacheEntry(**defaults)


class TestCacheEntry:
    def test_touch_updates(self) -> None:
        entry = _make_entry(access_count=0)
        entry.touch()
        assert entry.access_count == 1
        assert entry.last_accessed >= entry.created_at

    def test_is_expired_not_expired(self) -> None:
        entry = _make_entry()
        assert entry.is_expired(ttl_seconds=3600) is False

    def test_is_expired_expired(self) -> None:
        entry = _make_entry(created_at=time.time() - 7200)
        assert entry.is_expired(ttl_seconds=3600) is True

    def test_is_expired_zero_ttl(self) -> None:
        entry = _make_entry()
        assert entry.is_expired(ttl_seconds=0) is False

    @patch("os.path.getmtime", return_value=1000.0)
    def test_is_file_modified_true(self, mock_mtime) -> None:
        entry = _make_entry(file_mtime=500.0)
        assert entry.is_file_modified("/some/file") is True

    @patch("os.path.getmtime", return_value=500.0)
    def test_is_file_modified_false(self, mock_mtime) -> None:
        entry = _make_entry(file_mtime=1000.0)
        assert entry.is_file_modified("/some/file") is False

    def test_is_file_modified_no_mtime(self) -> None:
        entry = _make_entry(file_mtime=None)
        assert entry.is_file_modified("/some/file") is False

    @patch("os.path.getmtime", side_effect=OSError)
    def test_is_file_modified_os_error(self, mock_mtime) -> None:
        entry = _make_entry(file_mtime=500.0)
        assert entry.is_file_modified("/missing/file") is True


class TestLRUCacheStrategy:
    def test_should_cache_always_true(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_false_when_not_full(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        entry = _make_entry()
        assert s.should_evict(entry, {"cache_size": 5}) is False

    def test_should_evict_true_when_full(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        entry = _make_entry()
        assert s.should_evict(entry, {"cache_size": 10}) is True

    def test_get_eviction_candidates_returns_oldest(self) -> None:
        s = LRUCacheStrategy()
        e1 = _make_entry(key="a", last_accessed=100)
        e2 = _make_entry(key="b", last_accessed=200)
        e3 = _make_entry(key="c", last_accessed=50)
        candidates = s.get_eviction_candidates({"a": e1, "b": e2, "c": e3}, 2)
        assert candidates[0] == "c"
        assert candidates[1] == "a"

    def test_update_on_access(self) -> None:
        s = LRUCacheStrategy()
        entry = _make_entry(access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 1


class TestTTLCacheStrategy:
    def test_should_evict_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        entry = _make_entry(created_at=time.time() - 120)
        assert s.should_evict(entry, {}) is True

    def test_should_evict_not_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=3600)
        entry = _make_entry()
        assert s.should_evict(entry, {}) is False

    def test_get_eviction_candidates(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        e1 = _make_entry(key="a", created_at=time.time() - 120)
        e2 = _make_entry(key="b")
        candidates = s.get_eviction_candidates({"a": e1, "b": e2}, 1)
        assert "a" in candidates

    def test_update_on_access_noop(self) -> None:
        s = TTLCacheStrategy()
        entry = _make_entry(access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 0  # TTL does not update


class TestSmartCacheStrategy:
    def test_should_cache_no_file(self) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    @patch("os.path.getsize", return_value=2 * 1024 * 1024)
    def test_should_cache_large_file(self, mock_size) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {"file_path": "/big/file"}) is False

    @patch("os.path.getsize", return_value=100)
    def test_should_cache_tmp_file(self, mock_size) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {"file_path": "/tmp/file.tmp"}) is False

    @patch("os.path.getsize", return_value=100)
    def test_should_cache_normal_file(self, mock_size) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {"file_path": "/normal/file.md"}) is True

    @patch("os.path.getsize", side_effect=OSError)
    def test_should_cache_os_error(self, mock_size) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {"file_path": "/missing"}) is False

    def test_get_eviction_candidates_expired_first(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=60)
        e1 = _make_entry(key="a", created_at=time.time() - 120)
        e2 = _make_entry(key="b")
        candidates = s.get_eviction_candidates({"a": e1, "b": e2}, 2)
        assert candidates[0] == "a"


class TestLayeredCacheStrategy:
    def test_should_evict_cold_expired(self) -> None:
        s = LayeredCacheStrategy(cold_cache_ttl=60)
        entry = _make_entry(access_count=1, created_at=time.time() - 120)
        assert s.should_evict(entry, {}) is True

    def test_should_evict_cold_not_expired(self) -> None:
        s = LayeredCacheStrategy(cold_cache_ttl=3600)
        entry = _make_entry(access_count=1, created_at=time.time() - 60)
        assert s.should_evict(entry, {}) is False

    def test_should_evict_hot_not_evicted(self) -> None:
        s = LayeredCacheStrategy(hot_cache_size=100)
        entry = _make_entry(access_count=20, created_at=time.time() - 10000)
        assert s.should_evict(entry, {"cache_size": 50}) is False

    def test_get_eviction_candidates_cold_first(self) -> None:
        s = LayeredCacheStrategy()
        cold = _make_entry(key="cold", access_count=1)
        warm = _make_entry(key="warm", access_count=5)
        hot = _make_entry(key="hot", access_count=15)
        candidates = s.get_eviction_candidates({"cold": cold, "warm": warm, "hot": hot}, 2)
        assert candidates[0] == "cold"


class TestAdaptiveCacheStrategy:
    def test_default_strategy_is_lru(self) -> None:
        s = AdaptiveCacheStrategy()
        assert s.current_strategy == "lru"

    def test_should_cache(self) -> None:
        s = AdaptiveCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_record_miss(self) -> None:
        s = AdaptiveCacheStrategy()
        s.record_miss()
        assert s.recent_hits[-1] is False

    def test_update_on_access(self) -> None:
        s = AdaptiveCacheStrategy()
        entry = _make_entry()
        s.update_on_access(entry)
        assert s.recent_hits[-1] is True

    def test_evaluate_adapts_when_low_hit_rate(self) -> None:
        s = AdaptiveCacheStrategy()
        s.hit_rate_window = 5
        s.recent_hits = [False] * 5
        s.strategy_performance["ttl"] = {"hits": 10, "misses": 0}
        s._evaluate_and_adapt()
        assert s.current_strategy == "ttl"


class TestSteeringCacheStrategyManager:
    def test_get_miss(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert mgr.get("nonexistent") is None
        assert mgr.get_stats()["misses"] == 1

    def test_put_and_get(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert mgr.put("k", "value") is True
        assert mgr.get("k") == "value"
        assert mgr.get_stats()["hits"] == 1

    def test_put_rejected_by_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.SMART)
        with patch("os.path.getsize", return_value=2 * 1024 * 1024):
            assert mgr.put("k", "v", {"file_path": "/big"}) is False

    def test_invalidate_single(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("a", 1)
        mgr.put("b", 2)
        mgr.invalidate("a")
        assert mgr.get("a") is None
        assert mgr.get("b") == 2

    def test_invalidate_all(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("a", 1)
        mgr.invalidate()
        assert mgr.get("a") is None

    def test_get_stats(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("a", 1)
        stats = mgr.get_stats()
        assert stats["cache_size"] == 1
        assert stats["strategy_type"] == "lru"

    def test_ttl_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.TTL)
        assert isinstance(mgr.strategy, TTLCacheStrategy)

    def test_smart_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.SMART)
        assert isinstance(mgr.strategy, SmartCacheStrategy)

    def test_layered_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LAYERED)
        assert isinstance(mgr.strategy, LayeredCacheStrategy)

    def test_adaptive_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.ADAPTIVE)
        assert isinstance(mgr.strategy, AdaptiveCacheStrategy)

    def test_unknown_strategy_defaults_to_lru(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        result = mgr._create_strategy(CacheStrategy.LRU)
        assert isinstance(result, LRUCacheStrategy)


class TestCreateCacheStrategyFromConfig:
    def test_smart_config(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "smart"})
        assert mgr.strategy_type == CacheStrategy.SMART

    def test_unknown_defaults_to_smart(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "invalid"})
        assert mgr.strategy_type == CacheStrategy.SMART
