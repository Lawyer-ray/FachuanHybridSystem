"""
Extended unit tests for core/config/steering/cache_strategies.py

Covers:
  - CacheStrategy enum values
  - CacheEntry: touch, is_expired, is_file_modified edge cases
  - LRUCacheStrategy: should_cache, should_evict, get_eviction_candidates, update_on_access
  - TTLCacheStrategy: should_evict, get_eviction_candidates with insufficient expired
  - SmartCacheStrategy: should_cache (large file, .tmp/.log, OSError),
    should_evict (expired, file modified), get_eviction_candidates (mixed priorities)
  - LayeredCacheStrategy: should_evict (cold expired, cache overflow), get_eviction_candidates
  - AdaptiveCacheStrategy: should_cache/delegate, should_evict/delegate,
    update_on_access (hit rate window), record_miss, _evaluate_and_adapt,
    _find_best_strategy
  - SteeringCacheStrategyManager: get/miss, get/hit, get/eviction, put/should_cache,
    put/eviction, invalidate (single key, all keys), get_stats, _estimate_size
  - create_cache_strategy_from_config
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(key: str = "k", data: str = "data", **kwargs) -> CacheEntry:
    now = time.time()
    defaults = {
        "key": key, "data": data, "created_at": now, "last_accessed": now,
        "access_count": 1, "file_mtime": None, "size_bytes": 100, "priority": 0,
    }
    defaults.update(kwargs)
    return CacheEntry(**defaults)


# ===========================================================================
# CacheStrategy enum
# ===========================================================================


class TestCacheStrategyEnum:
    def test_values(self) -> None:
        assert CacheStrategy.LRU.value == "lru"
        assert CacheStrategy.TTL.value == "ttl"
        assert CacheStrategy.SMART.value == "smart"
        assert CacheStrategy.LAYERED.value == "layered"
        assert CacheStrategy.ADAPTIVE.value == "adaptive"


# ===========================================================================
# CacheEntry edge cases
# ===========================================================================


class TestCacheEntryEdge:
    def test_is_file_modified_oserror(self) -> None:
        entry = _make_entry(file_mtime=100.0)
        with patch("os.path.getmtime", side_effect=OSError("permission denied")):
            assert entry.is_file_modified("/some/file") is True

    def test_is_file_modified_file_not_found(self) -> None:
        entry = _make_entry(file_mtime=100.0)
        with patch("os.path.getmtime", side_effect=FileNotFoundError):
            assert entry.is_file_modified("/some/file") is True

    def test_is_expired_negative_ttl(self) -> None:
        entry = _make_entry()
        assert entry.is_expired(ttl_seconds=-1) is False


# ===========================================================================
# LRUCacheStrategy
# ===========================================================================


class TestLRUCacheStrategy:
    def test_should_cache_always_true(self) -> None:
        s = LRUCacheStrategy()
        assert s.should_cache("k", "d", {}) is True

    def test_should_evict_when_full(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        assert s.should_evict(_make_entry(), {"cache_size": 10}) is True

    def test_should_evict_when_not_full(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        assert s.should_evict(_make_entry(), {"cache_size": 5}) is False

    def test_get_eviction_candidates(self) -> None:
        s = LRUCacheStrategy()
        now = time.time()
        entries = {
            "old": _make_entry(key="old", last_accessed=now - 100),
            "new": _make_entry(key="new", last_accessed=now),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert candidates == ["old"]

    def test_update_on_access(self) -> None:
        s = LRUCacheStrategy()
        entry = _make_entry(access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 1


# ===========================================================================
# TTLCacheStrategy
# ===========================================================================


class TestTTLCacheStrategy:
    def test_should_evict_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        entry = _make_entry(created_at=time.time() - 120)
        assert s.should_evict(entry, {}) is True

    def test_should_evict_not_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        entry = _make_entry()
        assert s.should_evict(entry, {}) is False

    def test_get_eviction_candidates_enough_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        now = time.time()
        entries = {
            "expired1": _make_entry(key="expired1", created_at=now - 120),
            "expired2": _make_entry(key="expired2", created_at=now - 120),
            "fresh": _make_entry(key="fresh"),
        }
        candidates = s.get_eviction_candidates(entries, 2)
        assert len(candidates) == 2

    def test_get_eviction_candidates_insufficient_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        now = time.time()
        entries = {
            "expired": _make_entry(key="expired", created_at=now - 120),
            "old_fresh": _make_entry(key="old_fresh", created_at=now - 50),
            "new_fresh": _make_entry(key="new_fresh"),
        }
        candidates = s.get_eviction_candidates(entries, 3)
        # 1 expired + some from the remaining (sorted by created_at, oldest first)
        assert len(candidates) >= 1

    def test_update_on_access_noop(self) -> None:
        s = TTLCacheStrategy()
        entry = _make_entry(access_count=5)
        s.update_on_access(entry)
        assert entry.access_count == 5  # unchanged


# ===========================================================================
# SmartCacheStrategy
# ===========================================================================


class TestSmartCacheStrategy:
    def test_should_cache_no_file_path(self) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "d", {}) is True

    def test_should_cache_large_file(self) -> None:
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=2 * 1024 * 1024):
            assert s.should_cache("k", "d", {"file_path": "/big/file.txt"}) is False

    def test_should_cache_tmp_file(self) -> None:
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=100):
            assert s.should_cache("k", "d", {"file_path": "/file.tmp"}) is False

    def test_should_cache_log_file(self) -> None:
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=100):
            assert s.should_cache("k", "d", {"file_path": "/file.log"}) is False

    def test_should_cache_oserror(self) -> None:
        s = SmartCacheStrategy()
        with patch("os.path.getsize", side_effect=OSError):
            assert s.should_cache("k", "d", {"file_path": "/missing"}) is False

    def test_should_evict_expired(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=60)
        entry = _make_entry(created_at=time.time() - 120)
        assert s.should_evict(entry, {}) is True

    def test_should_evict_file_modified(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=3600, check_file_mtime=True)
        entry = _make_entry(file_mtime=100.0)
        with patch("os.path.getmtime", return_value=200.0):
            assert s.should_evict(entry, {"file_path": "/file"}) is True

    def test_should_evict_no_file_path(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=3600, check_file_mtime=True)
        entry = _make_entry()
        assert s.should_evict(entry, {}) is False

    def test_get_eviction_candidates_mixed(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=60)
        now = time.time()
        entries = {
            "expired": _make_entry(key="expired", created_at=now - 120, access_count=10),
            "low_freq": _make_entry(key="low_freq", access_count=1, last_accessed=now - 50),
            "high_freq": _make_entry(key="high_freq", access_count=100),
        }
        candidates = s.get_eviction_candidates(entries, 3)
        assert len(candidates) == 3

    def test_update_on_access(self) -> None:
        s = SmartCacheStrategy()
        entry = _make_entry(access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 1


# ===========================================================================
# LayeredCacheStrategy
# ===========================================================================


class TestLayeredCacheStrategy:
    def test_should_cache_always(self) -> None:
        s = LayeredCacheStrategy()
        assert s.should_cache("k", "d", {}) is True

    def test_should_evict_cold_expired(self) -> None:
        s = LayeredCacheStrategy(cold_cache_ttl=60)
        entry = _make_entry(access_count=1, created_at=time.time() - 120)
        assert s.should_evict(entry, {}) is True

    def test_should_evict_cold_not_expired(self) -> None:
        s = LayeredCacheStrategy(cold_cache_ttl=3600)
        entry = _make_entry(access_count=1)
        assert s.should_evict(entry, {}) is False

    def test_should_evict_cache_overflow(self) -> None:
        s = LayeredCacheStrategy(hot_cache_size=10, warm_cache_size=20)
        entry = _make_entry(access_count=1)
        assert s.should_evict(entry, {"cache_size": 35}) is True

    def test_should_evict_hot_in_overflow(self) -> None:
        s = LayeredCacheStrategy(hot_cache_size=10, warm_cache_size=20)
        entry = _make_entry(access_count=10)
        assert s.should_evict(entry, {"cache_size": 35}) is False

    def test_get_eviction_candidates_cold_first(self) -> None:
        s = LayeredCacheStrategy()
        now = time.time()
        entries = {
            "cold": _make_entry(key="cold", access_count=1, last_accessed=now - 100),
            "warm": _make_entry(key="warm", access_count=5, last_accessed=now - 50),
            "hot": _make_entry(key="hot", access_count=20, last_accessed=now),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert candidates[0] == "cold"

    def test_get_eviction_candidates_cascading(self) -> None:
        s = LayeredCacheStrategy()
        now = time.time()
        entries = {
            "cold1": _make_entry(key="cold1", access_count=1, last_accessed=now - 100),
            "cold2": _make_entry(key="cold2", access_count=1, last_accessed=now - 90),
            "warm1": _make_entry(key="warm1", access_count=5, last_accessed=now - 50),
            "hot1": _make_entry(key="hot1", access_count=20, last_accessed=now),
        }
        candidates = s.get_eviction_candidates(entries, 4)
        assert len(candidates) == 4


# ===========================================================================
# AdaptiveCacheStrategy
# ===========================================================================


class TestAdaptiveCacheStrategy:
    def test_should_cache_delegates(self) -> None:
        s = AdaptiveCacheStrategy()
        assert s.should_cache("k", "d", {}) is True

    def test_should_evict_delegates(self) -> None:
        s = AdaptiveCacheStrategy()
        s.current_strategy = "ttl"
        entry = _make_entry(created_at=time.time() - 7200)
        assert s.should_evict(entry, {}) is True

    def test_get_eviction_candidates_delegates(self) -> None:
        s = AdaptiveCacheStrategy()
        now = time.time()
        entries = {"old": _make_entry(key="old", last_accessed=now - 100)}
        result = s.get_eviction_candidates(entries, 1)
        assert result == ["old"]

    def test_update_on_access_tracks_hits(self) -> None:
        s = AdaptiveCacheStrategy()
        entry = _make_entry(access_count=0)
        for _ in range(101):
            s.update_on_access(entry)
        assert len(s.recent_hits) == 100  # window size

    def test_record_miss(self) -> None:
        s = AdaptiveCacheStrategy()
        s.record_miss()
        assert s.recent_hits == [False]

    def test_evaluate_and_adapt_switches_strategy(self) -> None:
        s = AdaptiveCacheStrategy()
        s.current_strategy = "lru"
        # Fill with all misses to trigger low hit rate
        s.recent_hits = [False] * 100
        s.strategy_performance["ttl"]["hits"] = 80
        s.strategy_performance["ttl"]["misses"] = 20
        s._evaluate_and_adapt()
        assert s.current_strategy == "ttl"

    def test_evaluate_and_adapt_no_switch_if_good_rate(self) -> None:
        s = AdaptiveCacheStrategy()
        s.current_strategy = "lru"
        s.recent_hits = [True] * 100
        s._evaluate_and_adapt()
        assert s.current_strategy == "lru"

    def test_find_best_strategy_no_data(self) -> None:
        s = AdaptiveCacheStrategy()
        s.current_strategy = "lru"
        s.strategy_performance = {"lru": {"hits": 0, "misses": 0}, "ttl": {"hits": 0, "misses": 0}, "smart": {"hits": 0, "misses": 0}}
        result = s._find_best_strategy()
        assert result == "lru"  # stays with current


# ===========================================================================
# SteeringCacheStrategyManager
# ===========================================================================


class TestSteeringCacheStrategyManager:
    def test_put_and_get(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "value1")
        assert mgr.get("k1") == "value1"

    def test_get_miss(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert mgr.get("missing") is None
        assert mgr._stats["misses"] == 1

    def test_get_hit(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        result = mgr.get("k1")
        assert result == "v1"
        assert mgr._stats["hits"] == 1

    def test_get_eviction_on_access(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.TTL)
        # Put with old creation time
        now = time.time()
        entry = CacheEntry(key="old", data="v", created_at=now - 7200, last_accessed=now - 7200, access_count=1)
        mgr._cache["old"] = entry
        result = mgr.get("old")
        assert result is None
        assert mgr._stats["evictions"] >= 1

    def test_put_rejects_by_strategy(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.SMART)
        with patch.object(mgr.strategy, "should_cache", return_value=False):
            result = mgr.put("k", "v")
        assert result is False

    def test_put_triggers_eviction_when_full(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        # Fill to capacity
        for i in range(1000):
            mgr._cache[f"k{i}"] = CacheEntry(
                key=f"k{i}", data=f"v{i}", created_at=time.time(), last_accessed=time.time() - i, access_count=1
            )
        mgr.put("new_key", "new_val")
        assert "new_key" in mgr._cache

    def test_invalidate_single_key(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.put("k2", "v2")
        mgr.invalidate("k1")
        assert mgr.get("k1") is None
        assert mgr.get("k2") == "v2"

    def test_invalidate_all(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.put("k2", "v2")
        mgr.invalidate()
        assert mgr.get("k1") is None
        assert mgr.get("k2") is None

    def test_get_stats(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.get("k1")
        stats = mgr.get_stats()
        assert stats["strategy_type"] == "lru"
        assert stats["hits"] == 1
        assert stats["cache_size"] == 1
        assert stats["hit_rate"] == 1.0

    def test_get_stats_no_requests(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        stats = mgr.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_estimate_size(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        size = mgr._estimate_size("test string")
        assert size > 0

    def test_create_with_file_metadata(self) -> None:
        mgr = SteeringCacheStrategyManager(CacheStrategy.SMART)
        with patch("os.path.getsize", return_value=100):
            with patch("os.path.getmtime", return_value=1000.0):
                result = mgr.put("k1", "v1", metadata={"file_path": "/test/file.txt"})
        assert result is True


# ===========================================================================
# create_cache_strategy_from_config
# ===========================================================================


class TestCreateCacheStrategyFromConfig:
    def test_valid_strategy(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "lru"})
        assert isinstance(mgr.strategy, LRUCacheStrategy)

    def test_unknown_strategy_uses_smart(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "unknown"})
        assert isinstance(mgr.strategy, SmartCacheStrategy)

    def test_default_strategy(self) -> None:
        mgr = create_cache_strategy_from_config({})
        assert isinstance(mgr.strategy, SmartCacheStrategy)

    def test_all_strategies(self) -> None:
        for name, expected_type in [
            ("lru", LRUCacheStrategy),
            ("ttl", TTLCacheStrategy),
            ("smart", SmartCacheStrategy),
            ("layered", LayeredCacheStrategy),
            ("adaptive", AdaptiveCacheStrategy),
        ]:
            mgr = create_cache_strategy_from_config({"strategy": name})
            assert isinstance(mgr.strategy, expected_type)
