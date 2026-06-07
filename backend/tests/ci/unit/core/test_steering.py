"""测试 core.config.steering 子模块

覆盖: dependency_manager.py, cache_strategies.py
"""
from __future__ import annotations

import time
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.steering.cache_strategies import (
    AdaptiveCacheStrategy,
    CacheEntry,
    CacheStrategy,
    CacheStrategyInterface,
    LayeredCacheStrategy,
    LRUCacheStrategy,
    SmartCacheStrategy,
    SteeringCacheStrategyManager,
    TTLCacheStrategy,
    create_cache_strategy_from_config,
)
from apps.core.config.steering.dependency_manager import (
    DependencyConflict,
    DependencyGraph,
    DependencyInfo,
    DependencyType,
    LoadOrderResult,
    LoadOrderStrategy,
    SpecificationMetadata,
    SteeringDependencyManager,
    create_dependency_manager_from_config,
)


# ============================================================
# CacheEntry
# ============================================================


class TestCacheEntry:
    """测试 CacheEntry 数据类"""

    def test_touch_updates_access(self) -> None:
        entry = CacheEntry(
            key="k", data="v", created_at=time.time(), last_accessed=time.time(), access_count=0
        )
        old_last = entry.last_accessed
        time.sleep(0.01)
        entry.touch()
        assert entry.access_count == 1
        assert entry.last_accessed >= old_last

    def test_is_expired_false_when_ttl_zero(self) -> None:
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert entry.is_expired(0) is False

    def test_is_expired_true(self) -> None:
        entry = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time() - 100)
        assert entry.is_expired(50) is True

    def test_is_expired_false_when_within_ttl(self) -> None:
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert entry.is_expired(3600) is False

    @patch("apps.core.config.steering.cache_strategies.os.path.getmtime")
    def test_is_file_modified_true(self, mock_getmtime: MagicMock) -> None:
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, file_mtime=100.0)
        mock_getmtime.return_value = 200.0
        assert entry.is_file_modified("/some/file") is True

    @patch("apps.core.config.steering.cache_strategies.os.path.getmtime")
    def test_is_file_modified_false(self, mock_getmtime: MagicMock) -> None:
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, file_mtime=200.0)
        mock_getmtime.return_value = 100.0
        assert entry.is_file_modified("/some/file") is False

    @patch("apps.core.config.steering.cache_strategies.os.path.getmtime")
    def test_is_file_modified_no_mtime(self, mock_getmtime: MagicMock) -> None:
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, file_mtime=None)
        assert entry.is_file_modified("/some/file") is False

    @patch("apps.core.config.steering.cache_strategies.os.path.getmtime")
    def test_is_file_modified_file_missing(self, mock_getmtime: MagicMock) -> None:
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, file_mtime=100.0)
        mock_getmtime.side_effect = FileNotFoundError
        assert entry.is_file_modified("/missing/file") is True


# ============================================================
# LRUCacheStrategy
# ============================================================


class TestLRUCacheStrategy:
    def test_should_cache_always_true(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_when_full(self) -> None:
        s = LRUCacheStrategy(max_entries=5)
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0)
        assert s.should_evict(entry, {"cache_size": 5}) is True
        assert s.should_evict(entry, {"cache_size": 3}) is False

    def test_get_eviction_candidates_by_last_accessed(self) -> None:
        s = LRUCacheStrategy(max_entries=10)
        entries = {
            "old": CacheEntry(key="old", data="d", created_at=0, last_accessed=1.0),
            "new": CacheEntry(key="new", data="d", created_at=0, last_accessed=100.0),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert candidates == ["old"]

    def test_update_on_access(self) -> None:
        s = LRUCacheStrategy()
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 1


# ============================================================
# TTLCacheStrategy
# ============================================================


class TestTTLCacheStrategy:
    def test_should_cache_always_true(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=60)
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=10)
        entry = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time())
        assert s.should_evict(entry, {}) is True

    def test_should_evict_not_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=3600)
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time())
        assert s.should_evict(entry, {}) is False

    def test_get_eviction_candidates_returns_expired(self) -> None:
        s = TTLCacheStrategy(ttl_seconds=10)
        entries = {
            "expired": CacheEntry(key="expired", data="d", created_at=time.time() - 100, last_accessed=time.time()),
            "fresh": CacheEntry(key="fresh", data="d", created_at=time.time(), last_accessed=time.time()),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert "expired" in candidates

    def test_update_on_access_is_noop(self) -> None:
        s = TTLCacheStrategy()
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0, access_count=0)
        s.update_on_access(entry)
        assert entry.access_count == 0  # TTL 不更新访问计数


# ============================================================
# SmartCacheStrategy
# ============================================================


class TestSmartCacheStrategy:
    def test_should_cache_no_file_path(self) -> None:
        s = SmartCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    @patch("apps.core.config.steering.cache_strategies.os.path.getsize")
    def test_should_cache_large_file(self, mock_getsize: MagicMock) -> None:
        s = SmartCacheStrategy()
        mock_getsize.return_value = 2 * 1024 * 1024  # 2MB
        assert s.should_cache("k", "v", {"file_path": "/big/file"}) is False

    @patch("apps.core.config.steering.cache_strategies.os.path.getsize")
    def test_should_cache_tmp_file(self, mock_getsize: MagicMock) -> None:
        s = SmartCacheStrategy()
        mock_getsize.return_value = 100
        assert s.should_cache("k", "v", {"file_path": "/path/file.tmp"}) is False

    def test_should_evict_expired_entry(self) -> None:
        s = SmartCacheStrategy(ttl_seconds=10)
        entry = CacheEntry(key="k", data="v", created_at=time.time() - 100, last_accessed=time.time())
        assert s.should_evict(entry, {}) is True


# ============================================================
# LayeredCacheStrategy
# ============================================================


class TestLayeredCacheStrategy:
    def test_should_cache_always_true(self) -> None:
        s = LayeredCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_should_evict_cold_expired(self) -> None:
        s = LayeredCacheStrategy(cold_cache_ttl=10)
        entry = CacheEntry(
            key="k", data="v", created_at=time.time() - 100, last_accessed=time.time(), access_count=1
        )
        assert s.should_evict(entry, {"cache_size": 10}) is True

    def test_should_evict_when_over_capacity(self) -> None:
        s = LayeredCacheStrategy(hot_cache_size=5, warm_cache_size=10)
        entry = CacheEntry(key="k", data="v", created_at=time.time(), last_accessed=time.time(), access_count=1)
        assert s.should_evict(entry, {"cache_size": 20}) is True

    def test_get_eviction_candidates_prefers_cold(self) -> None:
        s = LayeredCacheStrategy()
        entries = {
            "cold": CacheEntry(key="cold", data="d", created_at=0, last_accessed=1.0, access_count=1),
            "hot": CacheEntry(key="hot", data="d", created_at=0, last_accessed=100.0, access_count=20),
        }
        candidates = s.get_eviction_candidates(entries, 1)
        assert candidates[0] == "cold"


# ============================================================
# AdaptiveCacheStrategy
# ============================================================


class TestAdaptiveCacheStrategy:
    def test_initial_strategy_is_lru(self) -> None:
        s = AdaptiveCacheStrategy()
        assert s.current_strategy == "lru"

    def test_should_cache(self) -> None:
        s = AdaptiveCacheStrategy()
        assert s.should_cache("k", "v", {}) is True

    def test_record_miss(self) -> None:
        s = AdaptiveCacheStrategy()
        s.record_miss()
        assert False in s.recent_hits

    def test_update_on_access_records_hit(self) -> None:
        s = AdaptiveCacheStrategy()
        entry = CacheEntry(key="k", data="v", created_at=0, last_accessed=0)
        s.update_on_access(entry)
        assert True in s.recent_hits


# ============================================================
# SteeringCacheStrategyManager
# ============================================================


class TestSteeringCacheStrategyManager:
    def test_put_and_get(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.LRU)
        assert mgr.put("key1", "value1") is True
        assert mgr.get("key1") == "value1"

    def test_get_miss(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.LRU)
        assert mgr.get("nonexistent") is None

    def test_invalidate_single(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.LRU)
        mgr.put("key1", "value1")
        mgr.invalidate("key1")
        assert mgr.get("key1") is None

    def test_invalidate_all(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.LRU)
        mgr.put("a", 1)
        mgr.put("b", 2)
        mgr.invalidate()
        assert mgr.get("a") is None
        assert mgr.get("b") is None

    def test_get_stats(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.LRU)
        mgr.put("k", "v")
        mgr.get("k")
        mgr.get("miss")
        stats = mgr.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["cache_size"] == 1
        assert stats["strategy_type"] == "lru"

    def test_ttl_strategy_eviction(self) -> None:
        mgr = SteeringCacheStrategyManager(strategy_type=CacheStrategy.TTL)
        # TTL 默认 3600s, 正常条目不会过期
        mgr.put("key1", "data")
        assert mgr.get("key1") == "data"


class TestCreateCacheStrategyFromConfig:
    def test_default_strategy(self) -> None:
        mgr = create_cache_strategy_from_config({})
        assert isinstance(mgr, SteeringCacheStrategyManager)

    def test_lru_strategy(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "lru"})
        assert mgr.strategy_type == CacheStrategy.LRU

    def test_unknown_strategy_falls_back(self) -> None:
        mgr = create_cache_strategy_from_config({"strategy": "unknown"})
        assert mgr.strategy_type == CacheStrategy.SMART


# ============================================================
# DependencyGraph
# ============================================================


class TestDependencyGraph:
    def test_add_specification(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(
            path="a.md", name="A", requires=["b.md"]
        )
        graph.add_specification(meta)
        assert "a.md" in graph.nodes

    def test_get_dependencies(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        deps = graph.get_dependencies("a.md")
        assert len(deps) == 1
        assert deps[0].target_spec == "b.md"
        assert deps[0].dependency_type == DependencyType.REQUIRES

    def test_get_dependencies_filtered_by_type(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(
            path="a.md", name="A", requires=["b.md"], optional_deps=["c.md"]
        ))
        requires = graph.get_dependencies("a.md", [DependencyType.REQUIRES])
        assert len(requires) == 1
        optional = graph.get_dependencies("a.md", [DependencyType.OPTIONAL])
        assert len(optional) == 1

    def test_get_dependencies_nonexistent(self) -> None:
        graph = DependencyGraph()
        assert graph.get_dependencies("nonexistent.md") == []

    def test_get_dependents(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        dependents = graph.get_dependents("b.md")
        assert len(dependents) == 1
        assert dependents[0].source_spec == "a.md"

    def test_detect_circular_dependencies_none(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        cycles = graph.detect_circular_dependencies()
        assert len(cycles) == 0

    def test_detect_circular_dependencies_found(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B", requires=["a.md"]))
        cycles = graph.detect_circular_dependencies()
        assert len(cycles) > 0

    def test_topological_sort_linear(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A"))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B", requires=["a.md"]))
        ordered, conflicts = graph.topological_sort(["a.md", "b.md"])
        assert ordered.index("a.md") < ordered.index("b.md")
        assert len(conflicts) == 0

    def test_validate_dependencies_missing(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["missing.md"]))
        conflicts = graph.validate_dependencies(["a.md"])
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == "missing"

    def test_validate_dependencies_conflict(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", conflicts=["b.md"]))
        conflicts = graph.validate_dependencies(["a.md", "b.md"])
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == "conflict"

    def test_get_dependency_levels(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A"))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B", requires=["a.md"]))
        levels = graph.get_dependency_levels(["a.md", "b.md"])
        assert levels["a.md"] == 0
        assert levels["b.md"] == 1


# ============================================================
# SteeringDependencyManager
# ============================================================


class TestSteeringDependencyManager:
    def _make_manager(self, config: dict | None = None):
        """创建一个不加载文件的 DependencyManager"""
        with patch.object(SteeringDependencyManager, "_load_all_metadata"):
            return SteeringDependencyManager(config or {}, steering_root="/nonexistent")

    def test_init_defaults(self) -> None:
        mgr = self._make_manager()
        assert mgr.auto_resolve is True
        assert mgr.max_depth == 10
        assert mgr.circular_detection is True
        assert mgr.load_order_strategy == LoadOrderStrategy.DEPENDENCY

    def test_normalize_dependency_list_string(self) -> None:
        mgr = self._make_manager()
        assert mgr._normalize_dependency_list("single") == ["single"]

    def test_normalize_dependency_list_list(self) -> None:
        mgr = self._make_manager()
        assert mgr._normalize_dependency_list(["a", "b"]) == ["a", "b"]

    def test_normalize_dependency_list_invalid(self) -> None:
        mgr = self._make_manager()
        assert mgr._normalize_dependency_list(123) == []

    def test_get_dependency_info_nonexistent(self) -> None:
        mgr = self._make_manager()
        result = mgr.get_dependency_info("nonexistent.md")
        assert "error" in result

    def test_get_dependency_info_existing(self) -> None:
        mgr = self._make_manager()
        meta = SpecificationMetadata(path="a.md", name="A", requires=["b.md"])
        mgr._metadata_cache["a.md"] = meta
        mgr.dependency_graph.add_specification(meta)
        info = mgr.get_dependency_info("a.md")
        assert info["metadata"]["name"] == "A"
        assert "inherits" in info["dependencies"]

    def test_get_statistics_empty(self) -> None:
        mgr = self._make_manager()
        stats = mgr.get_statistics()
        assert stats["total_specifications"] == 0
        assert stats["total_dependencies"] == 0

    def test_get_statistics_with_specs(self) -> None:
        mgr = self._make_manager()
        meta = SpecificationMetadata(path="a.md", name="A", requires=["b.md"])
        mgr._metadata_cache["a.md"] = meta
        mgr.dependency_graph.add_specification(meta)
        stats = mgr.get_statistics()
        assert stats["total_specifications"] == 1

    def test_resolve_load_order_priority_strategy(self) -> None:
        mgr = self._make_manager({"load_order_strategy": "priority"})
        mgr._metadata_cache["a.md"] = SpecificationMetadata(path="a.md", name="A", priority=10)
        mgr._metadata_cache["b.md"] = SpecificationMetadata(path="b.md", name="B", priority=1)
        result = mgr.resolve_load_order(["a.md", "b.md"])
        assert result.ordered_specs[0] == "a.md"

    def test_resolve_load_order_alphabetical_strategy(self) -> None:
        mgr = self._make_manager({"load_order_strategy": "alphabetical"})
        result = mgr.resolve_load_order(["b.md", "a.md"])
        assert result.ordered_specs == ["a.md", "b.md"]


class TestCreateDependencyManagerFromConfig:
    def test_creates_manager(self) -> None:
        with patch.object(SteeringDependencyManager, "_load_all_metadata"):
            mgr = create_dependency_manager_from_config({}, "/nonexistent")
            assert isinstance(mgr, SteeringDependencyManager)
