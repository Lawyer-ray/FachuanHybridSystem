"""测试 core.telemetry 子模块

覆盖: metrics.py, time.py, context.py
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# time.py
# ============================================================


class TestTelemetryTime:
    """测试 time.py 工具函数"""

    def test_utc_now(self) -> None:
        from apps.core.telemetry.time import utc_now

        now = utc_now()
        assert now is not None
        assert now.tzinfo is not None

    def test_utc_now_iso(self) -> None:
        from apps.core.telemetry.time import utc_now_iso

        iso = utc_now_iso()
        assert iso.endswith("Z")
        assert "T" in iso


# ============================================================
# context.py
# ============================================================


class TestTelemetryContext:
    """测试 context.py"""

    def test_get_request_id(self) -> None:
        from apps.core.telemetry.context import get_request_id

        rid = get_request_id()
        assert isinstance(rid, str)


# ============================================================
# metrics.py - 纯函数
# ============================================================


class TestMetricsHelpers:
    """测试 metrics 模块的辅助函数"""

    def test_normalize_path_group_basic(self) -> None:
        from apps.core.telemetry.metrics import normalize_path_group

        assert normalize_path_group("/api/v1/cases") == "/api/v1/cases"

    def test_normalize_path_group_uuid(self) -> None:
        from apps.core.telemetry.metrics import normalize_path_group

        # max_segments=3, UUID 在第 2 段 (0-indexed) => 会被 normalize
        result = normalize_path_group("/api/550e8400-e29b-41d4-a716-446655440000/cases")
        assert ":id" in result

    def test_normalize_path_group_numeric_id(self) -> None:
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/api/12345/details")
        assert ":id" in result

    def test_normalize_path_group_hex_id(self) -> None:
        from apps.core.telemetry.metrics import normalize_path_group

        result = normalize_path_group("/api/abcdef1234567890abcdef1234567890/files")
        assert ":id" in result

    def test_normalize_path_group_empty(self) -> None:
        from apps.core.telemetry.metrics import normalize_path_group

        assert normalize_path_group("") == "/"
        assert normalize_path_group("/") == "/"

    def test_status_class(self) -> None:
        from apps.core.telemetry.metrics import _status_class

        assert _status_class(200) == "2xx"
        assert _status_class(404) == "4xx"
        assert _status_class(500) == "5xx"
        assert _status_class(0) == "0xx"

    def test_stable_hash(self) -> None:
        from apps.core.telemetry.metrics import _stable_hash

        h1 = _stable_hash({"a": 1, "b": 2})
        h2 = _stable_hash({"b": 2, "a": 1})  # 不同的 key 顺序
        assert h1 == h2  # sort_keys=True
        assert len(h1) == 16

    def test_normalize_label(self) -> None:
        from apps.core.telemetry.metrics import _normalize_label

        assert _normalize_label("GET", default="unknown", max_len=16) == "get"
        assert _normalize_label("", default="unknown", max_len=16) == "unknown"
        assert _normalize_label("  spaces  ", default="x", max_len=16) == "spaces"

    def test_normalize_label_special_chars(self) -> None:
        from apps.core.telemetry.metrics import _normalize_label

        result = _normalize_label("hello world!@#", default="x", max_len=32)
        assert "!" not in result
        assert "@" not in result

    def test_minute_id_format(self) -> None:
        from apps.core.telemetry.metrics import _minute_id

        mid = _minute_id()
        assert len(mid) == 12  # YYYYMMDDHHmm
        assert mid.isdigit()


# ============================================================
# metrics.py - Histogram
# ============================================================


class TestHistogram:
    """测试 Histogram 数据类"""

    def test_quantile_ms_empty(self) -> None:
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(buckets_ms=(10, 50, 100), counts={}, total_count=0, total_sum_ms=0)
        assert h.quantile_ms(0.5) == 0
        assert h.avg_ms == 0.0

    def test_quantile_ms(self) -> None:
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(
            buckets_ms=(10, 50, 100, 500),
            counts={10: 5, 50: 3, 100: 1, 500: 1},
            total_count=10,
            total_sum_ms=300,
        )
        # p50 = 第5个, 在 bucket 10 中
        assert h.quantile_ms(0.5) <= 50
        assert h.avg_ms == 30.0

    def test_quantile_ms_p99(self) -> None:
        from apps.core.telemetry.metrics import Histogram

        h = Histogram(
            buckets_ms=(10, 50, 100, 500, 1000),
            counts={10: 90, 50: 5, 100: 3, 500: 1, 1000: 1},
            total_count=100,
            total_sum_ms=5000,
        )
        assert h.quantile_ms(0.99) >= 100


# ============================================================
# metrics.py - _merge_histograms
# ============================================================


class TestMergeHistograms:
    def test_merge(self) -> None:
        from apps.core.telemetry.metrics import Histogram, _merge_histograms

        buckets = (10, 50, 100)
        h1 = Histogram(buckets_ms=buckets, counts={10: 1, 50: 2, 100: 0}, total_count=3, total_sum_ms=100)
        h2 = Histogram(buckets_ms=buckets, counts={10: 0, 50: 1, 100: 1}, total_count=2, total_sum_ms=150)
        merged = _merge_histograms([h1, h2], buckets_ms=buckets)
        assert merged.total_count == 5
        assert merged.total_sum_ms == 250
        assert merged.counts[50] == 3

    def test_merge_empty(self) -> None:
        from apps.core.telemetry.metrics import Histogram, _merge_histograms

        buckets = (10, 50)
        merged = _merge_histograms([], buckets_ms=buckets)
        assert merged.total_count == 0
        assert merged.total_sum_ms == 0


# ============================================================
# metrics.py - _top_slowest / _top_errors
# ============================================================


class TestTopFunctions:
    def test_top_slowest(self) -> None:
        from apps.core.telemetry.metrics import _top_slowest

        rows = [
            {"route_group": "/slow", "p95_ms": 5000, "count": 10},
            {"route_group": "/fast", "p95_ms": 10, "count": 100},
        ]
        result = _top_slowest(rows, 1)
        assert result[0]["route_group"] == "/slow"

    def test_top_errors(self) -> None:
        from apps.core.telemetry.metrics import _top_errors

        rows = [
            {"route_group": "/err", "status_class": "5xx", "count": 50, "p95_ms": 100},
            {"route_group": "/ok", "status_class": "2xx", "count": 100, "p95_ms": 50},
        ]
        result = _top_errors(rows, 10)
        assert len(result) == 1
        assert result[0]["route_group"] == "/err"

    def test_top_errors_include_error_class(self) -> None:
        from apps.core.telemetry.metrics import _top_errors

        rows = [
            {"route_group": "/err", "status_class": "error", "count": 50, "p95_ms": 100},
        ]
        result = _top_errors(rows, 10, include_error_class=True)
        assert len(result) == 1

    def test_top_errors_empty(self) -> None:
        from apps.core.telemetry.metrics import _top_errors

        assert _top_errors([], 10) == []


# ============================================================
# metrics.py - _histogram_summary
# ============================================================


class TestHistogramSummary:
    def test_summary(self) -> None:
        from apps.core.telemetry.metrics import Histogram, _histogram_summary

        h = Histogram(
            buckets_ms=(10, 50, 100),
            counts={10: 5, 50: 3, 100: 2},
            total_count=10,
            total_sum_ms=500,
        )
        summary = _histogram_summary(h)
        assert summary["count"] == 10
        assert summary["avg_ms"] == 50.0
        assert "p50_ms" in summary
        assert "p95_ms" in summary
        assert "p99_ms" in summary
