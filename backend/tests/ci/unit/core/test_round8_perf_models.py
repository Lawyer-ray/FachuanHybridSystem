"""Tests for _perf_models (PerformanceThresholds and dataclasses)."""

from __future__ import annotations

import pytest

from apps.core.config.steering._perf_models import (
    AlertLevel,
    PerformanceMetric,
    PerformanceAlert,
    LoadingPerformanceData,
    PerformanceThresholds,
)


# ---------------------------------------------------------------------------
# AlertLevel
# ---------------------------------------------------------------------------


class TestAlertLevel:
    def test_values(self):
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestPerformanceMetric:
    def test_basic(self):
        pm = PerformanceMetric(name="load_time", value=100.0, unit="ms", timestamp=1.0)
        assert pm.name == "load_time"
        assert pm.value == 100.0
        assert pm.metadata == {}

    def test_with_metadata(self):
        pm = PerformanceMetric(name="test", value=1.0, unit="s", timestamp=1.0, metadata={"key": "val"})
        assert pm.metadata == {"key": "val"}


class TestPerformanceAlert:
    def test_basic(self):
        pa = PerformanceAlert(
            level=AlertLevel.WARNING,
            message="high load time",
            metric_name="load_time",
            threshold=500.0,
            actual_value=600.0,
            timestamp=1.0,
        )
        assert pa.level == AlertLevel.WARNING
        assert pa.actual_value == 600.0


class TestLoadingPerformanceData:
    def test_basic(self):
        lpd = LoadingPerformanceData(
            spec_path="test.yaml",
            start_time=1.0,
            end_time=2.0,
            duration_ms=1000.0,
            success=True,
        )
        assert lpd.success is True
        assert lpd.cache_hit is False
        assert lpd.error_message is None

    def test_with_error(self):
        lpd = LoadingPerformanceData(
            spec_path="test.yaml",
            start_time=1.0,
            end_time=2.0,
            duration_ms=1000.0,
            success=False,
            error_message="parse error",
        )
        assert lpd.success is False
        assert lpd.error_message == "parse error"


# ---------------------------------------------------------------------------
# PerformanceThresholds
# ---------------------------------------------------------------------------


class TestPerformanceThresholds:
    def test_defaults(self):
        pt = PerformanceThresholds({})
        assert pt.load_time_warning_ms == 500.0
        assert pt.load_time_error_ms == 2000.0
        assert pt.load_time_critical_ms == 5000.0
        assert pt.memory_usage_warning_mb == 100.0
        assert pt.memory_usage_error_mb == 500.0
        assert pt.memory_usage_critical_mb == 1000.0
        assert pt.cache_hit_rate_warning == 0.7
        assert pt.cache_hit_rate_error == 0.5
        assert pt.concurrent_loads_warning == 10
        assert pt.concurrent_loads_error == 20

    def test_custom(self):
        pt = PerformanceThresholds({
            "load_time_warning_ms": 100.0,
            "load_time_error_ms": 500.0,
            "load_time_critical_ms": 1000.0,
            "memory_usage_warning_mb": 50.0,
            "memory_usage_error_mb": 200.0,
            "memory_usage_critical_mb": 500.0,
            "cache_hit_rate_warning": 0.9,
            "cache_hit_rate_error": 0.8,
            "concurrent_loads_warning": 5,
            "concurrent_loads_error": 10,
        })
        assert pt.load_time_warning_ms == 100.0
        assert pt.concurrent_loads_error == 10
        assert pt.cache_hit_rate_warning == 0.9
