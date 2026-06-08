"""core/performance 模块单元测试（_perf_collector, _perf_monitor）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.steering._perf_models import (
    AlertLevel,
    LoadingPerformanceData,
    PerformanceAlert,
    PerformanceThresholds,
)


class TestPerformanceThresholds:
    def test_defaults(self) -> None:
        t = PerformanceThresholds({})
        assert t.load_time_warning_ms > 0
        assert t.load_time_error_ms > t.load_time_warning_ms
        assert t.load_time_critical_ms > t.load_time_error_ms

    def test_custom_values(self) -> None:
        t = PerformanceThresholds({"load_time_warning_ms": 100})
        assert t.load_time_warning_ms == 100


class TestAlertLevel:
    def test_values(self) -> None:
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"


class TestLoadingPerformanceData:
    def test_creation(self) -> None:
        data = LoadingPerformanceData(
            spec_path="test.md",
            start_time=1.0,
            end_time=2.0,
            duration_ms=1000.0,
            success=True,
            cache_hit=False,
            file_size_bytes=100,
            memory_usage_mb=50.0,
        )
        assert data.spec_path == "test.md"
        assert data.success is True


class TestPerformanceAlert:
    def test_creation(self) -> None:
        alert = PerformanceAlert(
            level=AlertLevel.WARNING,
            message="test alert",
            metric_name="load_time_ms",
            threshold=100.0,
            actual_value=150.0,
            timestamp=1.0,
        )
        assert alert.level == AlertLevel.WARNING
        assert alert.message == "test alert"


@patch("apps.core.config.steering._perf_collector.psutil")
class TestPerformanceDataCollector:
    def test_init(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector(max_history_size=100)
        assert collector.max_history_size == 100
        assert collector._total_loads == 0

    def test_record_loading_start_end(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.md")
        assert load_id is not None
        data = collector.record_loading_end(load_id, "test.md", success=True)
        assert data.success is True
        assert collector._successful_loads == 1

    def test_record_loading_end_failure(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.md")
        data = collector.record_loading_end(load_id, "test.md", success=False, error_message="err")
        assert data.success is False
        assert collector._failed_loads == 1

    def test_get_loading_statistics_empty(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        stats = collector.get_loading_statistics()
        assert stats["total_loads"] == 0
        assert stats["success_rate"] == 0.0

    def test_get_loading_statistics_with_data(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        load_id = collector.record_loading_start("test.md")
        collector.record_loading_end(load_id, "test.md", success=True, cache_hit=True)
        stats = collector.get_loading_statistics()
        assert stats["total_loads"] == 1
        assert stats["cache_hits"] == 1

    def test_record_alert(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        alert = PerformanceAlert(
            level=AlertLevel.WARNING, message="test", metric_name="m", threshold=1.0, actual_value=2.0, timestamp=1.0
        )
        collector.record_alert(alert)
        assert len(collector.get_recent_alerts()) == 1

    def test_get_recent_alerts_limit(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        for i in range(5):
            alert = PerformanceAlert(
                level=AlertLevel.INFO, message=f"msg{i}", metric_name="m", threshold=1.0, actual_value=2.0, timestamp=float(i)
            )
            collector.record_alert(alert)
        assert len(collector.get_recent_alerts(3)) == 3

    def test_get_recent_loading_history(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_collector import PerformanceDataCollector

        collector = PerformanceDataCollector()
        for i in range(3):
            load_id = collector.record_loading_start(f"t{i}.md")
            collector.record_loading_end(load_id, f"t{i}.md", success=True)
        history = collector.get_recent_loading_history(2)
        assert len(history) == 2


@patch("apps.core.config.steering._perf_collector.psutil")
class TestSteeringPerformanceMonitor:
    def test_init_enabled(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        assert monitor.enabled is True

    def test_init_disabled(self, mock_psutil: MagicMock) -> None:
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": False})
        assert monitor.enabled is False

    def test_monitor_loading_when_disabled(self, mock_psutil: MagicMock) -> None:
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": False})
        result = monitor.monitor_loading("test.md", lambda: "result")
        assert result == "result"

    def test_monitor_loading_success(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        result = monitor.monitor_loading("test.md", lambda: "ok")
        assert result == "ok"

    def test_monitor_loading_failure(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        with pytest.raises(ValueError, match="boom"):
            monitor.monitor_loading("test.md", lambda: (_ for _ in ()).throw(ValueError("boom")))

    def test_get_performance_report_disabled(self, mock_psutil: MagicMock) -> None:
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": False})
        report = monitor.get_performance_report()
        assert report == {"enabled": False}

    def test_get_performance_report_enabled(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        report = monitor.get_performance_report()
        assert report["enabled"] is True
        assert "statistics" in report

    def test_add_alert_callback(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        cb = MagicMock()
        monitor.add_alert_callback(cb)
        assert cb in monitor.alert_callbacks

    def test_export_performance_data_disabled(self, mock_psutil: MagicMock) -> None:
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": False})
        monitor.export_performance_data("/tmp/test_perf.json")  # should not raise

    def test_shutdown(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        monitor = SteeringPerformanceMonitor({"enabled": True})
        monitor.shutdown()  # should not raise

    def test_create_from_config(self, mock_psutil: MagicMock) -> None:
        mock_psutil.Process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        from apps.core.config.steering._perf_monitor import create_performance_monitor_from_config

        monitor = create_performance_monitor_from_config({"enabled": False})
        assert monitor.enabled is False
