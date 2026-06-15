"""Tests for cache_strategies, evidence services, client services, and other pure-logic modules."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.steering.cache_strategies import (
    CacheEntry,
    CacheStrategy,
    LRUCacheStrategy,
    TTLCacheStrategy,
    SmartCacheStrategy,
    LayeredCacheStrategy,
    AdaptiveCacheStrategy,
    SteeringCacheStrategyManager,
    create_cache_strategy_from_config,
)
from apps.client.services.client_service_adapter import ClientServiceAdapter


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_touch(self):
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        old_count = entry.access_count
        entry.touch()
        assert entry.access_count == old_count + 1

    def test_is_expired(self):
        entry = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time())
        assert entry.is_expired(50) is True
        assert entry.is_expired(0) is False
        assert entry.is_expired(-1) is False

    def test_is_file_modified_no_mtime(self):
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert entry.is_file_modified("/nonexistent") is False

    def test_is_file_modified_nonexistent_file(self):
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time(), file_mtime=time.time())
        assert entry.is_file_modified("/nonexistent/file.txt") is True


# ---------------------------------------------------------------------------
# LRUCacheStrategy
# ---------------------------------------------------------------------------


class TestLRUCacheStrategy:
    def test_should_cache_always(self):
        s = LRUCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_when_full(self):
        s = LRUCacheStrategy(max_entries=5)
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert s.should_evict(entry, {"cache_size": 5}) is True
        assert s.should_evict(entry, {"cache_size": 4}) is False

    def test_get_eviction_candidates(self):
        s = LRUCacheStrategy()
        entries = {
            "old": CacheEntry(key="old", data="v", created_at=0, last_accessed=100),
            "new": CacheEntry(key="new", data="v", created_at=0, last_accessed=200),
            "mid": CacheEntry(key="mid", data="v", created_at=0, last_accessed=150),
        }
        candidates = s.get_eviction_candidates(entries, 2)
        assert candidates[0] == "old"

    def test_update_on_access(self):
        s = LRUCacheStrategy()
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=0)
        s.update_on_access(entry)
        assert entry.last_accessed > 0


# ---------------------------------------------------------------------------
# TTLCacheStrategy
# ---------------------------------------------------------------------------


class TestTTLCacheStrategy:
    def test_should_cache_always(self):
        s = TTLCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_expired(self):
        s = TTLCacheStrategy(ttl_seconds=60)
        expired = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time())
        fresh = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert s.should_evict(expired, {}) is True
        assert s.should_evict(fresh, {}) is False

    def test_get_eviction_candidates(self):
        s = TTLCacheStrategy(ttl_seconds=60)
        entries = {
            "expired": CacheEntry(key="expired", data="v", created_at=time.time() - 100, last_accessed=time.time()),
            "fresh": CacheEntry(key="fresh", data="v", created_at=time.time(), last_accessed=time.time()),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert "expired" in candidates

    def test_update_on_access_noop(self):
        s = TTLCacheStrategy()
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 0


# ---------------------------------------------------------------------------
# SmartCacheStrategy
# ---------------------------------------------------------------------------


class TestSmartCacheStrategy:
    def test_should_cache_no_path(self):
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_should_cache_large_file(self):
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=2 * 1024 * 1024):
            assert s.should_cache("k", "v", {"file_path": "/tmp/big.bin"}) is False

    def test_should_cache_tmp_file(self):
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=100):
            assert s.should_cache("k", "v", {"file_path": "/tmp/test.tmp"}) is False

    def test_should_cache_valid_file(self):
        s = SmartCacheStrategy()
        with patch("os.path.getsize", return_value=100):
            assert s.should_cache("k", "v", {"file_path": "/tmp/test.pdf"}) is True

    def test_should_cache_os_error(self):
        s = SmartCacheStrategy()
        with patch("os.path.getsize", side_effect=OSError):
            assert s.should_cache("k", "v", {"file_path": "/tmp/missing"}) is False

    def test_should_evict_expired(self):
        s = SmartCacheStrategy(ttl_seconds=60)
        expired = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time())
        assert s.should_evict(expired, {}) is True


# ---------------------------------------------------------------------------
# LayeredCacheStrategy
# ---------------------------------------------------------------------------


class TestLayeredCacheStrategy:
    def test_should_cache_always(self):
        s = LayeredCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_cold_expired(self):
        s = LayeredCacheStrategy(cold_cache_ttl=60)
        cold = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time(), access_count=1)
        assert s.should_evict(cold, {}) is True

    def test_should_evict_overflow(self):
        s = LayeredCacheStrategy(hot_cache_size=10, warm_cache_size=10)
        cold = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time(), access_count=0)
        assert s.should_evict(cold, {"cache_size": 25}) is True

    def test_get_eviction_candidates(self):
        s = LayeredCacheStrategy()
        entries = {
            "cold": CacheEntry(key="cold", data="v", created_at=0, last_accessed=100, access_count=0),
            "warm": CacheEntry(key="warm", data="v", created_at=0, last_accessed=200, access_count=5),
            "hot": CacheEntry(key="hot", data="v", created_at=0, last_accessed=300, access_count=15),
        }
        candidates = s.get_eviction_candidates(entries, 2)
        assert "cold" in candidates


# ---------------------------------------------------------------------------
# AdaptiveCacheStrategy
# ---------------------------------------------------------------------------


class TestAdaptiveCacheStrategy:
    def test_should_cache(self):
        s = AdaptiveCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_record_miss(self):
        s = AdaptiveCacheStrategy()
        s.record_miss()
        assert len(s.recent_hits) == 1
        assert s.recent_hits[0] is False

    def test_adapt_after_window(self):
        s = AdaptiveCacheStrategy()
        s.hit_rate_window = 5
        for _ in range(5):
            s.record_miss()
        # After window fills with misses, _evaluate_and_adapt is called
        # Current hit_rate = 0/5 = 0 < 0.7, but all strategies also have 0 hits
        # So best_strategy remains the current one


# ---------------------------------------------------------------------------
# SteeringCacheStrategyManager
# ---------------------------------------------------------------------------


class TestSteeringCacheStrategyManager:
    def test_create_lru(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert isinstance(mgr.strategy, LRUCacheStrategy)

    def test_create_ttl(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.TTL)
        assert isinstance(mgr.strategy, TTLCacheStrategy)

    def test_create_smart(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.SMART)
        assert isinstance(mgr.strategy, SmartCacheStrategy)

    def test_create_layered(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LAYERED)
        assert isinstance(mgr.strategy, LayeredCacheStrategy)

    def test_create_adaptive(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.ADAPTIVE)
        assert isinstance(mgr.strategy, AdaptiveCacheStrategy)

    def test_put_and_get(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert mgr.put("k1", "v1") is True
        assert mgr.get("k1") == "v1"

    def test_get_miss(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        assert mgr.get("nonexistent") is None

    def test_invalidate_key(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.invalidate("k1")
        assert mgr.get("k1") is None

    def test_invalidate_all(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.put("k2", "v2")
        mgr.invalidate()
        assert mgr.get("k1") is None
        assert mgr.get("k2") is None

    def test_get_stats(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        mgr.put("k1", "v1")
        mgr.get("k1")
        mgr.get("nonexistent")
        stats = mgr.get_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["cache_size"] >= 1

    def test_estimate_size(self):
        mgr = SteeringCacheStrategyManager(CacheStrategy.LRU)
        size = mgr._estimate_size("test data")
        assert size > 0


# ---------------------------------------------------------------------------
# create_cache_strategy_from_config
# ---------------------------------------------------------------------------


class TestCreateCacheStrategyFromConfig:
    def test_valid_strategy(self):
        mgr = create_cache_strategy_from_config({"strategy": "lru"})
        assert isinstance(mgr, SteeringCacheStrategyManager)

    def test_invalid_strategy_fallback(self):
        mgr = create_cache_strategy_from_config({"strategy": "unknown"})
        assert isinstance(mgr, SteeringCacheStrategyManager)

    def test_default_strategy(self):
        mgr = create_cache_strategy_from_config({})
        assert isinstance(mgr, SteeringCacheStrategyManager)


# ---------------------------------------------------------------------------
# ClientServiceAdapter
# ---------------------------------------------------------------------------


class TestClientServiceAdapter:
    def test_lazy_properties(self):
        adapter = ClientServiceAdapter()
        # Access properties to trigger lazy init
        assert adapter.dto_assembler is not None
        assert adapter.internal_query_service is not None
        assert adapter.related_dto_assembler is not None

    def test_get_client_none(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client(1)
        assert result is None

    def test_get_client_internal(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client_internal(1)
        assert result is None

    def test_validate_client_exists_false(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        assert adapter.validate_client_exists(1) is False

    def test_validate_client_exists_true(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = MagicMock()
        mock_dto_assembler = MagicMock()
        mock_dto_assembler.to_dto.return_value = MagicMock()
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            dto_assembler=mock_dto_assembler,
        )
        assert adapter.validate_client_exists(1) is True

    def test_get_clients_by_ids_empty(self):
        mock_query = MagicMock()
        mock_query.get_clients_by_ids.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_clients_by_ids([])
        assert result == []

    def test_get_client_by_name_none(self):
        mock_query = MagicMock()
        mock_query.get_client_by_name.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client_by_name("not found")
        assert result is None

    def test_get_all_clients_internal_empty(self):
        mock_query = MagicMock()
        mock_query.list_all_clients.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_all_clients_internal()
        assert result == []

    def test_search_clients_empty(self):
        mock_query = MagicMock()
        mock_query.search_clients_by_name.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.search_clients_by_name_internal("name")
        assert result == []

    def test_is_natural_person(self):
        mock_query = MagicMock()
        mock_query.is_natural_person.return_value = True
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        assert adapter.is_natural_person_internal(1) is True

    def test_get_property_clues_empty(self):
        mock_query = MagicMock()
        mock_query.list_property_clues_by_client.return_value = []
        mock_related = MagicMock()
        mock_related.property_clues_to_dtos.return_value = []
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            related_dto_assembler=mock_related,
        )
        result = adapter.get_property_clues_by_client_internal(1)
        assert result == []

    def test_get_identity_docs_empty(self):
        mock_query = MagicMock()
        mock_query.list_identity_docs_by_client.return_value = []
        mock_related = MagicMock()
        mock_related.identity_docs_to_dtos.return_value = []
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            related_dto_assembler=mock_related,
        )
        result = adapter.get_identity_docs_by_client_internal(1)
        assert result == []
