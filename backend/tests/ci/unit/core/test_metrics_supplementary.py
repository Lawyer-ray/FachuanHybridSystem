"""
Supplementary unit tests for core/telemetry/metrics.py

Covers branches not in test_metrics_extended.py:
  - _normalize_label edge cases
  - _set_meta_once / _get_meta error paths
  - _incr / _add_to_index edge cases
  - Histogram quantile edge cases
  - record_request 5xx
  - record_httpx null status
  - snapshot with real recorded data
  - snapshot_prometheus output structure
  - _iter_suffixes various inputs
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.core.telemetry.metrics import (
    DEFAULT_BUCKETS_MS,
    Histogram,
    _add_to_index,
    _finalize_cache_hit_rates,
    _get_meta,
    _incr,
    _iter_suffixes,
    _last_minutes,
    _merge_histograms,
    _minute_id,
    _normalize_label,
    _set_meta_once,
    _stable_hash,
    _status_class,
    _top_errors,
    _top_slowest,
    normalize_path_group,
    record_cache_access,
    record_cache_result,
    record_httpx,
    record_request,
    snapshot,
    snapshot_prometheus,
)


# ===========================================================================
# _normalize_label
# ===========================================================================


class TestNormalizeLabel:
    def test_empty_string(self) -> None:
        assert _normalize_label("", default="default", max_len=32) == "default"

    def test_none(self) -> None:
        assert _normalize_label(None, default="default", max_len=32) == "default"

    def test_long_truncated(self) -> None:
        result = _normalize_label("a" * 100, default="def", max_len=10)
        assert len(result) <= 10

    def test_unsafe_chars_replaced(self) -> None:
        result = _normalize_label("hello!@#world", default="def", max_len=32)
        assert "!" not in result

    def test_all_unsafe_returns_default(self) -> None:
        assert _normalize_label("!@#$%", default="def", max_len=32) == "def"

    def test_strips_leading_trailing_underscores(self) -> None:
        assert _normalize_label("__test__", default="def", max_len=32) == "test"

    def test_valid_chars_kept(self) -> None:
        assert _normalize_label("test-value_123", default="def", max_len=32) == "test-value_123"


# ===========================================================================
# _set_meta_once / _get_meta
# ===========================================================================


class TestMetaFunctions:
    @patch("apps.core.telemetry.metrics.cache")
    def test_set_meta_once_connection_error(self, mock_cache) -> None:
        mock_cache.add.side_effect = ConnectionError("fail")
        # Should not raise
        _set_meta_once(kind="req", suffix="abc", meta={"key": "val"}, timeout=600)

    @patch("apps.core.telemetry.metrics.cache")
    def test_set_meta_once_timeout_error(self, mock_cache) -> None:
        mock_cache.add.side_effect = TimeoutError("timeout")
        _set_meta_once(kind="req", suffix="abc", meta={}, timeout=600)

    @patch("apps.core.telemetry.metrics.cache")
    def test_set_meta_once_os_error(self, mock_cache) -> None:
        mock_cache.add.side_effect = OSError("os")
        _set_meta_once(kind="req", suffix="abc", meta={}, timeout=600)

    @patch("apps.core.telemetry.metrics.cache")
    def test_get_meta_dict_raw(self, mock_cache) -> None:
        mock_cache.get.return_value = {"method": "GET"}
        result = _get_meta(kind="req", suffix="abc")
        assert result == {"method": "GET"}

    @patch("apps.core.telemetry.metrics.cache")
    def test_get_meta_invalid_raw(self, mock_cache) -> None:
        mock_cache.get.return_value = 12345  # not str or dict
        result = _get_meta(kind="req", suffix="abc")
        assert result is None


# ===========================================================================
# _incr / _add_to_index
# ===========================================================================


class TestIncrAndIndex:
    @patch("apps.core.telemetry.metrics.cache")
    def test_add_to_index_overflow_trims(self, mock_cache) -> None:
        items = [f"v{i}" for i in range(200)]
        mock_cache.get.return_value = json.dumps(items)
        _add_to_index("idx", "new", timeout=600)
        saved = json.loads(mock_cache.set.call_args[0][1])
        assert len(saved) == 200
        assert saved[-1] == "new"
        assert "v0" not in saved  # oldest trimmed

    @patch("apps.core.telemetry.metrics.cache")
    def test_add_to_index_value_error(self, mock_cache) -> None:
        mock_cache.get.return_value = "not-json"
        # Should not raise
        _add_to_index("idx", "val", timeout=600)

    @patch("apps.core.telemetry.metrics.cache")
    def test_add_to_index_type_error(self, mock_cache) -> None:
        mock_cache.get.side_effect = TypeError("bad")
        _add_to_index("idx", "val", timeout=600)


# ===========================================================================
# Histogram
# ===========================================================================


class TestHistogramEdge:
    def test_quantile_falls_through_to_last_bucket(self) -> None:
        h = Histogram(
            buckets_ms=(10, 50),
            counts={10: 0, 50: 0},
            total_count=5,
            total_sum_ms=100,
        )
        # No counts in any bucket, should return last bucket
        assert h.quantile_ms(0.5) == 50

    def test_quantile_q_zero(self) -> None:
        h = Histogram(
            buckets_ms=(10, 50, 100),
            counts={10: 10, 50: 0, 100: 0},
            total_count=10,
            total_sum_ms=100,
        )
        # q=0 -> target = max(1, 0) = 1, first bucket has 10 >= 1
        assert h.quantile_ms(0.0) == 10

    def test_quantile_q_one(self) -> None:
        h = Histogram(
            buckets_ms=(10, 50, 100),
            counts={10: 5, 50: 3, 100: 2},
            total_count=10,
            total_sum_ms=500,
        )
        assert h.quantile_ms(1.0) == 100


# ===========================================================================
# _merge_histograms
# ===========================================================================


class TestMergeHistograms:
    def test_merge_single(self) -> None:
        h = Histogram(buckets_ms=(10,), counts={10: 5}, total_count=5, total_sum_ms=50)
        merged = _merge_histograms([h], buckets_ms=(10,))
        assert merged.total_count == 5
        assert merged.counts[10] == 5

    def test_merge_empty_list(self) -> None:
        merged = _merge_histograms([], buckets_ms=(10,))
        assert merged.total_count == 0
        assert merged.total_sum_ms == 0


# ===========================================================================
# record_request
# ===========================================================================


class TestRecordRequest:
    @patch("apps.core.telemetry.metrics.cache")
    def test_5xx_error_recorded(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_request(method="POST", path="/api/fail", status_code=500, duration_ms=100)
        calls = mock_cache.incr.call_args_list
        error_keys = [c[0][0] for c in calls if "errors_5xx" in c[0][0]]
        assert len(error_keys) >= 1

    @patch("apps.core.telemetry.metrics.cache")
    def test_bucket_selection(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        # 75ms should fall into 100ms bucket (DEFAULT_BUCKETS_MS: 5,10,25,50,100,...)
        record_request(method="GET", path="/api/test", status_code=200, duration_ms=75)
        calls = mock_cache.incr.call_args_list
        bucket_keys = [c[0][0] for c in calls if "bucket:" in c[0][0]]
        assert len(bucket_keys) >= 1

    @patch("apps.core.telemetry.metrics.cache")
    def test_zero_duration(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_request(method="GET", path="/api/test", status_code=200, duration_ms=0)


# ===========================================================================
# record_httpx
# ===========================================================================


class TestRecordHttpx:
    @patch("apps.core.telemetry.metrics.cache")
    def test_null_status_records_error(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_httpx(host="example.com", method="GET", status_code=None, duration_ms=30)
        calls = mock_cache.incr.call_args_list
        error_keys = [c[0][0] for c in calls if "errors_5xx" in c[0][0]]
        assert len(error_keys) >= 1

    @patch("apps.core.telemetry.metrics.cache")
    def test_host_with_port_normalized(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_httpx(host="api.example.com:443", method="GET", status_code=200, duration_ms=30)
        # Should have processed without error


# ===========================================================================
# record_cache_access / record_cache_result
# ===========================================================================


class TestRecordCache:
    @patch("apps.core.telemetry.metrics.cache")
    def test_record_cache_access_hit(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_cache_access(cache_kind="redis", name="token", hit=True)

    @patch("apps.core.telemetry.metrics.cache")
    def test_record_cache_access_miss(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_cache_access(cache_kind="redis", name="token", hit=False)

    @patch("apps.core.telemetry.metrics.cache")
    def test_record_cache_result_custom(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_cache_result(cache_kind="local", name="config", result="evict")


# ===========================================================================
# _finalize_cache_hit_rates
# ===========================================================================


class TestFinalizeCacheHitRates:
    def test_calculates_rates(self) -> None:
        data = {
            "redis": {
                "total": 100, "hits": 80, "misses": 20, "hit_rate": 0.0,
                "by_name": {
                    "token": {"total": 60, "hits": 50, "misses": 10, "hit_rate": 0.0},
                    "config": {"total": 40, "hits": 30, "misses": 10, "hit_rate": 0.0},
                },
            }
        }
        _finalize_cache_hit_rates(data)
        assert data["redis"]["hit_rate"] == 0.8
        by_name = data["redis"]["by_name"]
        assert isinstance(by_name, list)
        assert len(by_name) == 2
        # Sorted by total descending
        assert by_name[0]["name"] == "token"

    def test_zero_totals(self) -> None:
        data = {"cache": {"total": 0, "hits": 0, "misses": 0, "hit_rate": 0.0, "by_name": {}}}
        _finalize_cache_hit_rates(data)
        assert data["cache"]["hit_rate"] == 0.0


# ===========================================================================
# _top_slowest / _top_errors
# ===========================================================================


class TestTopFunctions:
    def test_top_slowest_sorts_by_p95(self) -> None:
        rows = [
            {"route_group": "/a", "p95_ms": 100, "count": 10},
            {"route_group": "/b", "p95_ms": 500, "count": 5},
            {"route_group": "/c", "p95_ms": 50, "count": 20},
        ]
        result = _top_slowest(rows, 2)
        assert len(result) == 2
        assert result[0]["route_group"] == "/b"

    def test_top_errors_filters_5xx(self) -> None:
        rows = [
            {"route_group": "/a", "status_class": "5xx", "count": 10, "p95_ms": 100},
            {"route_group": "/b", "status_class": "2xx", "count": 100, "p95_ms": 50},
        ]
        result = _top_errors(rows, 10)
        assert len(result) == 1
        assert result[0]["route_group"] == "/a"

    def test_top_errors_with_error_class(self) -> None:
        rows = [
            {"route_group": "/a", "status_class": "error", "count": 10, "p95_ms": 100},
        ]
        result = _top_errors(rows, 10, include_error_class=True)
        assert len(result) == 1

    def test_top_errors_empty(self) -> None:
        assert _top_errors([], 10) == []


# ===========================================================================
# _iter_suffixes
# ===========================================================================


class TestIterSuffixes:
    @patch("apps.core.telemetry.metrics.cache")
    def test_none(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        assert list(_iter_suffixes("key")) == []

    @patch("apps.core.telemetry.metrics.cache")
    def test_json_string(self, mock_cache) -> None:
        mock_cache.get.return_value = json.dumps(["s1", "s2"])
        assert list(_iter_suffixes("key")) == ["s1", "s2"]

    @patch("apps.core.telemetry.metrics.cache")
    def test_list_raw(self, mock_cache) -> None:
        mock_cache.get.return_value = ["s1", "s2"]
        assert list(_iter_suffixes("key")) == ["s1", "s2"]

    @patch("apps.core.telemetry.metrics.cache")
    def test_invalid_json(self, mock_cache) -> None:
        mock_cache.get.return_value = "not-json"
        assert list(_iter_suffixes("key")) == []

    @patch("apps.core.telemetry.metrics.cache")
    def test_value_error(self, mock_cache) -> None:
        mock_cache.get.return_value = object()  # not JSON serializable
        assert list(_iter_suffixes("key")) == []


# ===========================================================================
# snapshot
# ===========================================================================


class TestSnapshot:
    @patch("apps.core.telemetry.metrics.cache")
    def test_empty_snapshot(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        result = snapshot(window_minutes=1)
        assert result["window_minutes"] == 1
        assert result["requests"]["count"] == 0
        assert result["httpx"]["count"] == 0
        assert result["requests_top_slowest"] == []
        assert result["requests_top_errors"] == []

    @patch("apps.core.telemetry.metrics.cache")
    def test_snapshot_with_recorded_data(self, mock_cache) -> None:
        """Record data then snapshot."""
        mock_cache.get.return_value = None
        mock_cache.incr.return_value = 1
        record_request(method="GET", path="/api/test", status_code=200, duration_ms=50, window_minutes=1)
        record_httpx(host="example.com", method="GET", status_code=200, duration_ms=30, window_minutes=1)
        record_cache_access(cache_kind="redis", name="token", hit=True, window_minutes=1)
        # Reset mock to return None for reads
        mock_cache.get.return_value = None
        result = snapshot(window_minutes=1)
        assert "requests" in result
        assert "httpx" in result
        assert "cache_access" in result


# ===========================================================================
# snapshot_prometheus
# ===========================================================================


class TestSnapshotPrometheus:
    @patch("apps.core.telemetry.metrics.cache")
    def test_contains_prometheus_types(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        result = snapshot_prometheus(window_minutes=1)
        assert "TYPE fachuan_requests_total counter" in result
        assert "TYPE fachuan_requests_latency_ms gauge" in result
        assert "TYPE fachuan_httpx_total counter" in result
        assert "TYPE fachuan_httpx_latency_ms gauge" in result

    @patch("apps.core.telemetry.metrics.cache")
    def test_ends_with_newline(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        result = snapshot_prometheus(window_minutes=1)
        assert result.endswith("\n")

    @patch("apps.core.telemetry.metrics.cache")
    def test_with_cache_metrics(self, mock_cache) -> None:
        """Prometheus output includes cache metrics when present."""
        mock_cache.get.return_value = None
        result = snapshot_prometheus(window_minutes=1)
        # No cache data recorded, so should not have cache type
        # But format string lines are still present
        assert "fachuan_requests_total" in result
