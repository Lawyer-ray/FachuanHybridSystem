"""Extended tests for core.telemetry.metrics - covering record, snapshot, prometheus."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from apps.core.telemetry.metrics import (
    DEFAULT_BUCKETS_MS,
    Histogram,
    _add_to_index,
    _finalize_cache_hit_rates,
    _histogram_summary,
    _last_minutes,
    _load_counter,
    _load_histogram,
    _merge_histograms,
    _minute_id,
    _status_class,
    _stable_hash,
    normalize_path_group,
    record_cache_access,
    record_cache_result,
    record_httpx,
    record_request,
    snapshot,
    snapshot_prometheus,
)


class TestMinuteId:
    def test_returns_12_digits(self) -> None:
        result = _minute_id()
        assert len(result) == 12
        assert result.isdigit()

    def test_with_custom_dt(self) -> None:
        dt = datetime(2026, 3, 15, 10, 30)
        result = _minute_id(dt)
        assert result == "202603151030"


class TestLastMinutes:
    @patch("apps.core.telemetry.metrics.timezone")
    def test_returns_correct_count(self, mock_tz) -> None:
        mock_tz.now.return_value = datetime(2026, 3, 15, 10, 30)
        result = _last_minutes(window_minutes=3)
        assert len(result) == 3
        # Should be in reverse chronological then reversed -> ascending
        assert result == sorted(result)

    @patch("apps.core.telemetry.metrics.timezone")
    def test_window_of_1(self, mock_tz) -> None:
        mock_tz.now.return_value = datetime(2026, 3, 15, 10, 30)
        result = _last_minutes(window_minutes=1)
        assert len(result) == 1

    @patch("apps.core.telemetry.metrics.timezone")
    def test_window_of_0_defaults_to_1(self, mock_tz) -> None:
        mock_tz.now.return_value = datetime(2026, 3, 15, 10, 30)
        result = _last_minutes(window_minutes=0)
        assert len(result) == 1


class TestNormalizePathGroup:
    def test_trailing_slash(self) -> None:
        assert normalize_path_group("/api/") == "/api"

    def test_max_segments_1(self) -> None:
        result = normalize_path_group("/api/v1/cases", max_segments=1)
        assert result == "/api"

    def test_hex_id_normalized(self) -> None:
        result = normalize_path_group("/api/abcdef1234567890abcdef1234567890/detail")
        assert ":id" in result

    def test_uuid_normalized(self) -> None:
        result = normalize_path_group("/api/550e8400-e29b-41d4-a716-446655440000/files")
        assert ":id" in result

    def test_empty_path(self) -> None:
        assert normalize_path_group("") == "/"
        assert normalize_path_group("/") == "/"

    def test_long_segment_truncated(self) -> None:
        long_seg = "a" * 100
        result = normalize_path_group(f"/api/{long_seg}")
        # Each segment is max 64 chars
        parts = result.split("/")
        assert len(parts[-1]) <= 64


class TestStatusClass:
    def test_200(self) -> None:
        assert _status_class(200) == "2xx"

    def test_404(self) -> None:
        assert _status_class(404) == "4xx"

    def test_500(self) -> None:
        assert _status_class(500) == "5xx"

    def test_503(self) -> None:
        assert _status_class(503) == "5xx"

    def test_type_error(self) -> None:
        assert _status_class("bad") == "unknown"  # type: ignore[arg-type]


class TestRecordRequest:
    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_records_count_and_sum(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_request(method="GET", path="/api/v1/cases", status_code=200, duration_ms=50)
        # Should have called incr for count and sum_ms
        assert mock_cache.incr.call_count >= 2

    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_records_5xx_error(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_request(method="POST", path="/api/v1/cases", status_code=500, duration_ms=100)
        # 5xx error counter should be incremented
        calls = [str(c) for c in mock_cache.incr.call_args_list]
        assert any("errors_5xx" in c for c in calls)


class TestRecordHttpx:
    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_records_count(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_httpx(host="example.com", method="GET", status_code=200, duration_ms=30)
        assert mock_cache.incr.call_count >= 2

    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_records_5xx_error(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_httpx(host="api.openai.com", method="POST", status_code=500, duration_ms=200)
        calls = [str(c) for c in mock_cache.incr.call_args_list]
        assert any("errors_5xx" in c for c in calls)

    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_records_none_status_as_error(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_httpx(host="api.openai.com", method="GET", status_code=None, duration_ms=5000)
        calls = [str(c) for c in mock_cache.incr.call_args_list]
        assert any("errors_5xx" in c for c in calls)


class TestRecordCacheResult:
    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_hit(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_cache_result(cache_kind="redis", name="user_profile", result="hit")
        assert mock_cache.incr.call_count >= 1

    @patch("apps.core.telemetry.metrics.cache")
    @patch("apps.core.telemetry.metrics._minute_id", return_value="202603151030")
    def test_miss(self, mock_minute, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.add.return_value = None
        mock_cache.incr.return_value = 1
        mock_cache.set.return_value = None

        record_cache_result(cache_kind="redis", name="user_profile", result="miss")
        assert mock_cache.incr.call_count >= 1


class TestRecordCacheAccess:
    @patch("apps.core.telemetry.metrics.record_cache_result")
    def test_hit(self, mock_record) -> None:
        record_cache_access(cache_kind="redis", name="config", hit=True)
        mock_record.assert_called_once_with(
            cache_kind="redis", name="config", result="hit", window_minutes=10
        )

    @patch("apps.core.telemetry.metrics.record_cache_result")
    def test_miss(self, mock_record) -> None:
        record_cache_access(cache_kind="redis", name="config", hit=False)
        mock_record.assert_called_once_with(
            cache_kind="redis", name="config", result="miss", window_minutes=10
        )


class TestAddToIndex:
    @patch("apps.core.telemetry.metrics.cache")
    def test_first_entry(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        _add_to_index("idx:key", "value1", timeout=60)
        mock_cache.set.assert_called_once()

    @patch("apps.core.telemetry.metrics.cache")
    def test_existing_entry(self, mock_cache) -> None:
        import json
        mock_cache.get.return_value = json.dumps(["value1"])
        mock_cache.set.return_value = None

        _add_to_index("idx:key", "value2", timeout=60)
        # Should append value2
        call_args = mock_cache.set.call_args
        data = json.loads(call_args[0][1])
        assert "value2" in data

    @patch("apps.core.telemetry.metrics.cache")
    def test_duplicate_entry(self, mock_cache) -> None:
        import json
        mock_cache.get.return_value = json.dumps(["value1"])
        mock_cache.set.return_value = None

        _add_to_index("idx:key", "value1", timeout=60)
        # Should not set again since value already exists
        mock_cache.set.assert_not_called()


class TestFinalizeCacheHitRates:
    def test_calculates_rates(self) -> None:
        data = {
            "redis": {"total": 100, "hits": 80, "misses": 20, "hit_rate": 0.0, "by_name": {
                "config": {"total": 50, "hits": 40, "misses": 10, "hit_rate": 0.0},
                "user": {"total": 50, "hits": 40, "misses": 10, "hit_rate": 0.0},
            }}
        }
        _finalize_cache_hit_rates(data)
        assert data["redis"]["hit_rate"] == 0.8
        # by_name should be sorted by total
        names = [e["name"] for e in data["redis"]["by_name"]]
        assert len(names) == 2

    def test_zero_total(self) -> None:
        data = {
            "redis": {"total": 0, "hits": 0, "misses": 0, "hit_rate": 0.0, "by_name": {}}
        }
        _finalize_cache_hit_rates(data)
        assert data["redis"]["hit_rate"] == 0.0


class TestLoadHistogram:
    @patch("apps.core.telemetry.metrics.cache")
    def test_loads_from_cache(self, mock_cache) -> None:
        mock_cache.get.side_effect = lambda k: {
            "metrics:req:m1:s1:count": 10,
            "metrics:req:m1:s1:sum_ms": 500,
            "metrics:req:m1:s1:bucket:10": 5,
            "metrics:req:m1:s1:bucket:50": 3,
            "metrics:req:m1:s1:bucket:100": 2,
        }.get(k)

        result = _load_histogram(minute="m1", kind="req", suffix="s1", buckets_ms=(10, 50, 100))
        assert result.total_count == 10
        assert result.total_sum_ms == 500
        assert result.counts[10] == 5


class TestLoadCounter:
    @patch("apps.core.telemetry.metrics.cache")
    def test_loads_count(self, mock_cache) -> None:
        mock_cache.get.return_value = 42
        result = _load_counter(minute="m1", kind="cache", suffix="s1")
        assert result == 42

    @patch("apps.core.telemetry.metrics.cache")
    def test_loads_none_returns_0(self, mock_cache) -> None:
        mock_cache.get.return_value = None
        result = _load_counter(minute="m1", kind="cache", suffix="s1")
        assert result == 0


class TestSnapshot:
    @patch("apps.core.telemetry.metrics._collect_cache_data", return_value={})
    @patch("apps.core.telemetry.metrics._collect_histogram_data")
    @patch("apps.core.telemetry.metrics._last_minutes", return_value=["m1", "m2"])
    def test_basic_snapshot(self, mock_minutes, mock_hist, mock_cache) -> None:
        empty_h = Histogram(buckets_ms=DEFAULT_BUCKETS_MS, counts={}, total_count=0, total_sum_ms=0)
        mock_hist.return_value = ({}, empty_h)

        result = snapshot(window_minutes=10)
        assert "requests" in result
        assert "httpx" in result
        assert "cache_access" in result

    @patch("apps.core.telemetry.metrics._collect_cache_data", return_value={})
    @patch("apps.core.telemetry.metrics._collect_histogram_data")
    @patch("apps.core.telemetry.metrics._last_minutes", return_value=["m1"])
    def test_snapshot_has_top_slowest(self, mock_minutes, mock_hist, mock_cache) -> None:
        empty_h = Histogram(buckets_ms=DEFAULT_BUCKETS_MS, counts={}, total_count=0, total_sum_ms=0)
        mock_hist.return_value = ({}, empty_h)

        result = snapshot(window_minutes=5, top=3)
        assert "requests_top_slowest" in result
        assert "httpx_top_slowest" in result


class TestSnapshotPrometheus:
    @patch("apps.core.telemetry.metrics.snapshot")
    def test_returns_prometheus_format(self, mock_snapshot) -> None:
        mock_snapshot.return_value = {
            "requests": {"count": 100, "avg_ms": 50, "p50_ms": 30, "p95_ms": 100, "p99_ms": 200},
            "httpx": {"count": 50, "avg_ms": 100, "p50_ms": 80, "p95_ms": 200, "p99_ms": 500},
            "cache_access": {
                "redis": {
                    "by_name": [
                        {"name": "config", "hits": 80, "misses": 20},
                        {"name": "user", "hits": 40, "misses": 10},
                    ]
                }
            },
        }
        result = snapshot_prometheus()
        assert "fachuan_requests_total 100" in result
        assert "fachuan_httpx_total 50" in result
        assert "fachuan_cache_access_total" in result
        assert 'result="hit"' in result
        assert 'result="miss"' in result

    @patch("apps.core.telemetry.metrics.snapshot")
    def test_empty_cache(self, mock_snapshot) -> None:
        mock_snapshot.return_value = {
            "requests": {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0},
            "httpx": {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0},
            "cache_access": {},
        }
        result = snapshot_prometheus()
        assert "fachuan_cache_access_total" not in result
