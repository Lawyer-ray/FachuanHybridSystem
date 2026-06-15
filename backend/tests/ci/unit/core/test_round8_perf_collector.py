"""Tests for _perf_models, _perf_collector, and _perf_analyzer."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from apps.core.config.steering._perf_models import (
    AlertLevel,
    PerformanceMetric,
    PerformanceAlert,
    LoadingPerformanceData,
    PerformanceThresholds,
)
from apps.core.config.steering._perf_collector import PerformanceDataCollector


# ---------------------------------------------------------------------------
# PerformanceDataCollector
# ---------------------------------------------------------------------------


class TestPerformanceDataCollector:
    def test_init(self):
        collector = PerformanceDataCollector(max_history_size=100)
        stats = collector.get_loading_statistics()
        assert stats["total_loads"] == 0
        assert stats["successful_loads"] == 0
        assert stats["cache_hits"] == 0

    def test_record_loading_start(self):
        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.yaml")
        assert "test.yaml" in load_id
        stats = collector.get_loading_statistics()
        assert stats["current_concurrent_loads"] == 1

    def test_record_loading_end_success(self):
        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.yaml")
        perf = collector.record_loading_end(
            load_id=load_id,
            spec_path="test.yaml",
            success=True,
            cache_hit=True,
        )
        assert perf.success is True
        assert perf.cache_hit is True
        stats = collector.get_loading_statistics()
        assert stats["successful_loads"] == 1
        assert stats["cache_hits"] == 1

    def test_record_loading_end_failure(self):
        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.yaml")
        perf = collector.record_loading_end(
            load_id=load_id,
            spec_path="test.yaml",
            success=False,
            error_message="parse error",
        )
        assert perf.success is False
        stats = collector.get_loading_statistics()
        assert stats["failed_loads"] == 1

    def test_record_metric(self):
        collector = PerformanceDataCollector()
        metric = PerformanceMetric(name="test", value=1.0, unit="ms", timestamp=time.time())
        collector.record_metric(metric)
        # Should not raise

    def test_record_alert(self):
        collector = PerformanceDataCollector()
        alert = PerformanceAlert(
            level=AlertLevel.WARNING,
            message="test alert",
            metric_name="test",
            threshold=100.0,
            actual_value=200.0,
            timestamp=time.time(),
        )
        collector.record_alert(alert)
        alerts = collector.get_recent_alerts()
        assert len(alerts) == 1
        assert alerts[0].message == "test alert"

    def test_get_recent_alerts_limit(self):
        collector = PerformanceDataCollector()
        for i in range(10):
            alert = PerformanceAlert(
                level=AlertLevel.INFO,
                message=f"alert {i}",
                metric_name="test",
                threshold=0,
                actual_value=i,
                timestamp=time.time(),
            )
            collector.record_alert(alert)
        recent = collector.get_recent_alerts(limit=3)
        assert len(recent) == 3

    def test_get_loading_statistics_empty(self):
        collector = PerformanceDataCollector()
        stats = collector.get_loading_statistics()
        assert stats["cache_hit_rate"] == 0.0
        assert stats["success_rate"] == 0.0
        assert stats["load_time_stats"]["avg_ms"] == 0.0

    def test_get_loading_statistics_with_data(self):
        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.yaml")
        collector.record_loading_end(load_id=load_id, spec_path="test.yaml", success=True, cache_hit=True)
        stats = collector.get_loading_statistics()
        assert stats["total_loads"] == 1
        assert stats["cache_hit_rate"] == 1.0
        assert stats["success_rate"] == 1.0

    def test_get_recent_loading_history(self):
        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.yaml")
        collector.record_loading_end(load_id=load_id, spec_path="test.yaml", success=True)
        history = collector.get_recent_loading_history()
        assert len(history) == 1
        assert history[0].spec_path == "test.yaml"

    def test_invalid_load_id(self):
        collector = PerformanceDataCollector()
        perf = collector.record_loading_end(
            load_id="invalid_id",
            spec_path="test.yaml",
            success=True,
        )
        assert perf.duration_ms == 0.0
