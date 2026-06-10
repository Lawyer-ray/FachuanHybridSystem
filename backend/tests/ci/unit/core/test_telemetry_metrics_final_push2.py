"""Tests for core/telemetry/metrics.py - targeting all uncovered branches."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone as tz


class TestMinuteId:
    """Test _minute_id."""

    def test_with_datetime(self):
        from apps.core.telemetry.metrics import _minute_id

        dt = datetime(2025, 6, 10, 14, 30, 0)
        assert _minute_id(dt) == "202506101430"

    def test_with_none(self):
        from apps.core.telemetry.metrics import _minute_id

        result = _minute_id(None)
        assert len(result) == 12  # YYYYMMDDHHMM format
        assert result.isdigit()


class TestLastMinutes:
    """Test _last_minutes."""

    def test_returns_correct_count(self):
        from apps.core.telemetry.metrics import _last_minutes

        minutes = _last_minutes(window_minutes=5)
        assert len(minutes) == 5

    def test_minimum_one(self):
        from apps.core.telemetry.metrics import _last_minutes

        minutes = _last_minutes(window_minutes=0)
        assert len(minutes) >= 1

    def test_returns_strings(self):
        from apps.core.telemetry.metrics import _last_minutes

        minutes = _last_minutes(window_minutes=3)
        for m in minutes:
            assert isinstance(m, str)
            assert len(m) == 12


class TestStableHash:
    """Test _stable_hash."""

    def test_deterministic(self):
        from apps.core.telemetry.metrics import _stable_hash

        data = {"kind": "req", "method": "GET"}
        assert _stable_hash(data) == _stable_hash(data)

    def test_different_data_different_hash(self):
        from apps.core.telemetry.metrics import _stable_hash

        h1 = _stable_hash({"a": 1})
        h2 = _stable_hash({"b": 2})
        assert h1 != h2

    def test_returns_16_chars(self):
        from apps.core.telemetry.metrics import _stable_hash

        result = _stable_hash({"test": True})
        assert len(result) == 16


class TestNormalizeLabel:
    """Test _normalize_label."""

    def test_normalizes_to_lowercase(self):
        from apps.core.telemetry.metrics import _normalize_label

        assert _normalize_label("Hello", default="d", max_len=32) == "hello"

    def test_replaces_special_chars(self):
        from apps.core.telemetry.metrics import _normalize_label

        result = _normalize_label("hello world!", default="d", max_len=32)
        assert " " not in result
        assert "!" not in result

    def test_returns_default_for_empty(self):
        from apps.core.telemetry.metrics import _normalize_label

        assert _normalize_label("", default="default", max_len=32) == "default"
        assert _normalize_label("   ", default="default", max_len=32) == "default"

    def test_returns_default_for_all_special(self):
        from apps.core.telemetry.metrics import _normalize_label

        assert _normalize_label("!!!", default="def", max_len=32) == "def"

    def test_truncates_to_max_len(self):
        from apps.core.telemetry.metrics import _normalize_label

        result = _normalize_label("verylonglabel", default="d", max_len=5)
        assert len(result) <= 5


class TestNormalizePathGroup:
    """Test normalize_path_group."""

    def test_normal_path(self):
        from apps.core.telemetry.metrics import normalize_path_group

        assert normalize_path_group("/clients/active") == "/clients/active"

    def test_numeric_ids_replaced(self):
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/clients/123")
        assert ":id" in result

    def test_uuid_replaced(self):
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/clients/550e8400-e29b-41d4-a716-446655440000")
        assert ":id" in result

    def test_hex_replaced(self):
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/clients/abcdef1234567890abcdef1234567890")
        assert ":id" in result

    def test_max_segments(self):
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/a/b/c/d/e", max_segments=2)
        parts = result.split("/")
        # root + 2 segments = 3 parts (after splitting empty first)
        assert len([p for p in parts if p]) <= 2

    def test_empty_path(self):
        from apps.core.telemetry.metrics import normalize_path_group

        assert normalize_path_group("") == "/"

    def test_long_segment_truncated(self):
        from apps.core.telemetry.metrics import normalize_path_group

        long_name = "a" * 100
        result = normalize_path_group(f"/{long_name}")
        # segment should be truncated to 64 chars
        assert "a" * 65 not in result


class TestStatusClass:
    """Test _status_class."""

    def test_200(self):
        from apps.core.telemetry.metrics import _status_class

        assert _status_class(200) == "2xx"

    def test_500(self):
        from apps.core.telemetry.metrics import _status_class

        assert _status_class(500) == "5xx"

    def test_404(self):
        from apps.core.telemetry.metrics import _status_class

        assert _status_class(404) == "4xx"

    def test_invalid_returns_unknown(self):
        from apps.core.telemetry.metrics import _status_class

        assert _status_class(None) == "unknown"  # type: ignore[arg-type]


class TestHistogram:
    """Test Histogram dataclass."""

    def test_quantile_ms_empty(self):
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(buckets_ms=(10, 50, 100), counts={}, total_count=0, total_sum_ms=0)
        assert h.quantile_ms(0.95) == 0

    def test_quantile_ms_returns_bucket(self):
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(
            buckets_ms=(10, 50, 100),
            counts={10: 5, 50: 3, 100: 2},
            total_count=10,
            total_sum_ms=500,
        )
        assert h.quantile_ms(0.5) == 10  # 5 out of 10 at 10ms

    def test_avg_ms_empty(self):
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(buckets_ms=(10,), counts={}, total_count=0, total_sum_ms=0)
        assert h.avg_ms == 0.0

    def test_avg_ms_computed(self):
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(buckets_ms=(10,), counts={10: 5}, total_count=5, total_sum_ms=500)
        assert h.avg_ms == 100.0


class TestMergeHistograms:
    """Test _merge_histograms."""

    def test_merges_two_histograms(self):
        from apps.core.telemetry.metrics import Histogram, _merge_histograms

        h1 = Histogram(buckets_ms=(10, 50), counts={10: 3, 50: 2}, total_count=5, total_sum_ms=100)
        h2 = Histogram(buckets_ms=(10, 50), counts={10: 1, 50: 4}, total_count=5, total_sum_ms=200)
        merged = _merge_histograms([h1, h2], buckets_ms=(10, 50))
        assert merged.total_count == 10
        assert merged.total_sum_ms == 300
        assert merged.counts[10] == 4
        assert merged.counts[50] == 6

    def test_merges_empty_list(self):
        from apps.core.telemetry.metrics import _merge_histograms

        merged = _merge_histograms([], buckets_ms=(10, 50))
        assert merged.total_count == 0


class TestRecordRequest:
    """Test record_request."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_basic_recording(self, mock_cache):
        from apps.core.telemetry.metrics import record_request

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_request(method="GET", path="/api/v1/clients", status_code=200, duration_ms=50)
        assert mock_cache.incr.called

    @patch("apps.core.telemetry.metrics.cache")
    def test_5xx_errors_recorded(self, mock_cache):
        from apps.core.telemetry.metrics import record_request

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_request(method="POST", path="/api/v1/test", status_code=500, duration_ms=100)
        # Check that errors_5xx counter was incremented
        calls = [str(c) for c in mock_cache.incr.call_args_list]
        errors_calls = [c for c in calls if "errors_5xx" in c]
        assert len(errors_calls) > 0


class TestRecordHttpx:
    """Test record_httpx."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_basic_recording(self, mock_cache):
        from apps.core.telemetry.metrics import record_httpx

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_httpx(host="api.example.com:443", method="GET", status_code=200, duration_ms=30)
        assert mock_cache.incr.called

    @patch("apps.core.telemetry.metrics.cache")
    def test_none_status_code_records_error(self, mock_cache):
        from apps.core.telemetry.metrics import record_httpx

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_httpx(host="api.example.com", method="GET", status_code=None, duration_ms=30)
        calls = [str(c) for c in mock_cache.incr.call_args_list]
        errors_calls = [c for c in calls if "errors_5xx" in c]
        assert len(errors_calls) > 0


class TestRecordCacheAccess:
    """Test record_cache_access and record_cache_result."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_record_hit(self, mock_cache):
        from apps.core.telemetry.metrics import record_cache_access

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_cache_access(cache_kind="redis", name="user_cache", hit=True)
        assert mock_cache.incr.called

    @patch("apps.core.telemetry.metrics.cache")
    def test_record_miss(self, mock_cache):
        from apps.core.telemetry.metrics import record_cache_access

        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        record_cache_access(cache_kind="redis", name="user_cache", hit=False)
        assert mock_cache.incr.called


class TestSnapshot:
    """Test snapshot."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_empty_snapshot(self, mock_cache):
        from apps.core.telemetry.metrics import snapshot

        mock_cache.get.return_value = None
        result = snapshot(window_minutes=5)
        assert "requests" in result
        assert "httpx" in result
        assert "cache_access" in result
        assert result["requests"]["count"] == 0

    @patch("apps.core.telemetry.metrics.cache")
    def test_snapshot_with_data(self, mock_cache):
        from apps.core.telemetry.metrics import snapshot

        def cache_get(key):
            if "index" in key:
                return '["abc123"]'
            if ":count" in key:
                return 5
            if ":sum_ms" in key:
                return 500
            if ":bucket:" in key:
                return 2
            if ":meta:" in key:
                return '{"method":"GET","status":"2xx","group":"/api/test"}'
            if ":errors_5xx" in key:
                return 0
            return None

        mock_cache.get.side_effect = cache_get
        mock_cache.add.return_value = True
        result = snapshot(window_minutes=1)
        assert result["requests"]["count"] > 0


class TestSnapshotPrometheus:
    """Test snapshot_prometheus."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_empty_prometheus_output(self, mock_cache):
        from apps.core.telemetry.metrics import snapshot_prometheus

        mock_cache.get.return_value = None
        output = snapshot_prometheus(window_minutes=1)
        assert "fachuan_requests_total" in output
        assert "fachuan_httpx_total" in output

    @patch("apps.core.telemetry.metrics.cache")
    def test_with_cache_data(self, mock_cache):
        from apps.core.telemetry.metrics import snapshot_prometheus

        def cache_get(key):
            if "index" in key and "cache" in key:
                return '["cache1"]'
            if ":count" in key:
                return 10
            if ":sum_ms" in key:
                return 1000
            if ":bucket:" in key:
                return 5
            if ":meta:" in key and "cache" in key:
                return '{"cache_kind":"redis","name":"user","result":"hit"}'
            if ":meta:" in key:
                return '{"method":"GET","status":"2xx","group":"/api"}'
            return None

        mock_cache.get.side_effect = cache_get
        mock_cache.add.return_value = True
        output = snapshot_prometheus(window_minutes=1)
        assert "fachuan_cache_access_total" in output


class TestTopHelpers:
    """Test _top_slowest and _top_errors."""

    def test_top_slowest_sorted(self):
        from apps.core.telemetry.metrics import _top_slowest

        rows = [
            {"route_group": "/a", "p95_ms": 100, "count": 5},
            {"route_group": "/b", "p95_ms": 200, "count": 3},
            {"route_group": "/c", "p95_ms": 50, "count": 10},
        ]
        result = _top_slowest(rows, 2)
        assert len(result) == 2
        assert result[0]["route_group"] == "/b"

    def test_top_errors_filters_5xx(self):
        from apps.core.telemetry.metrics import _top_errors

        rows = [
            {"route_group": "/a", "status_class": "2xx", "count": 5},
            {"route_group": "/b", "status_class": "5xx", "count": 3},
            {"route_group": "/c", "status_class": "5xx", "count": 10},
        ]
        result = _top_errors(rows, 5)
        assert len(result) == 2

    def test_top_errors_includes_error_class(self):
        from apps.core.telemetry.metrics import _top_errors

        rows = [
            {"route_group": "/a", "status_class": "error", "count": 5},
            {"route_group": "/b", "status_class": "2xx", "count": 3},
        ]
        result = _top_errors(rows, 5, include_error_class=True)
        assert len(result) == 1

    def test_top_errors_empty(self):
        from apps.core.telemetry.metrics import _top_errors

        rows = [{"route_group": "/a", "status_class": "2xx", "count": 5}]
        result = _top_errors(rows, 5)
        assert len(result) == 0


class TestBuildHistogramRows:
    """Test _build_histogram_rows."""

    @patch("apps.core.telemetry.metrics.cache")
    def test_builds_rows(self, mock_cache):
        from apps.core.telemetry.metrics import Histogram, _build_histogram_rows

        mock_cache.get.return_value = None
        merged = {
            "abc": Histogram(
                buckets_ms=(10, 50),
                counts={10: 5, 50: 3},
                total_count=8,
                total_sum_ms=200,
            )
        }
        rows = _build_histogram_rows(merged, "req", ("group", "route_group"))
        assert len(rows) == 1
        assert rows[0]["count"] == 8
