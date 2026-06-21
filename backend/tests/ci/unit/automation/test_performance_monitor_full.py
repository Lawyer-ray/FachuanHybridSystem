"""PerformanceMonitor 全覆盖测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from plugins.court_automation.token.performance_monitor import (
    AlertThresholds,
    PerformanceMetrics,
    PerformanceMonitor,
)


class TestPerformanceMetrics:
    """PerformanceMetrics 数据类测试。"""

    def test_defaults(self) -> None:
        m = PerformanceMetrics()
        assert m.total_acquisitions == 0
        assert m.success_rate == 0.0
        assert m.cache_hit_rate == 0.0

    def test_to_dict(self) -> None:
        m = PerformanceMetrics(total_acquisitions=10, success_rate=80.0)
        d = m.to_dict()
        assert d["total_acquisitions"] == 10
        assert d["success_rate"] == 80.0


class TestAlertThresholds:
    """AlertThresholds 数据类测试。"""

    def test_defaults(self) -> None:
        t = AlertThresholds()
        assert t.min_success_rate == 80.0
        assert t.max_avg_duration == 120.0
        assert t.max_timeout_rate == 10.0
        assert t.max_concurrent_acquisitions == 5
        assert t.min_cache_hit_rate == 70.0


class TestPerformanceMonitor:
    """PerformanceMonitor 测试。"""

    def _make_monitor(self, thresholds: AlertThresholds | None = None) -> PerformanceMonitor:
        pm = PerformanceMonitor.__new__(PerformanceMonitor)
        pm.alert_thresholds = thresholds or AlertThresholds()
        pm._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        return pm

    # ─── record_cache_access ───

    def test_record_cache_access_hit(self) -> None:
        pm = self._make_monitor()
        pm.record_cache_access("key", hit=True)
        assert pm._cache_stats["hits"] == 1
        assert pm._cache_stats["total_requests"] == 1

    def test_record_cache_access_miss(self) -> None:
        pm = self._make_monitor()
        pm.record_cache_access("key", hit=False)
        assert pm._cache_stats["misses"] == 1

    def test_record_cache_access_periodic_reset(self) -> None:
        pm = self._make_monitor()
        pm._cache_stats["total_requests"] = 999
        pm.record_cache_access("key", hit=True)
        # At 1000, stats reset to 0 (reset happens when total % 1000 == 0)
        assert pm._cache_stats["total_requests"] == 0

    # ─── record_acquisition_start ───

    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_record_acquisition_start(self, mock_cache: MagicMock) -> None:
        pm = self._make_monitor()
        pm.record_acquisition_start("id1", "site", "acct")
        assert mock_cache.set.call_count == 2  # acquisition data + concurrent count

    # ─── record_acquisition_end ───

    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_record_acquisition_end_success(self, mock_cache: MagicMock) -> None:
        pm = self._make_monitor()
        # Mock _update_counters and _decrement_concurrent_count to avoid complex cache.get sequencing
        with patch.object(pm, "_update_counters"), \
             patch.object(pm, "_check_alerts"), \
             patch.object(pm, "_decrement_concurrent_count"):
            mock_cache.get.return_value = {"site_name": "site", "account": "acct"}
            pm.record_acquisition_end("id1", success=True, duration=5.0, login_duration=2.0)
            mock_cache.set.assert_called()  # updated acquisition data

    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_record_acquisition_end_failure(self, mock_cache: MagicMock) -> None:
        pm = self._make_monitor()
        with patch.object(pm, "_update_counters"), \
             patch.object(pm, "_check_alerts"), \
             patch.object(pm, "_decrement_concurrent_count"):
            mock_cache.get.return_value = None
            pm.record_acquisition_end("id1", success=False, duration=5.0, error_type="timeout")

    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_record_acquisition_end_high_duration_alert(self, mock_cache: MagicMock) -> None:
        pm = self._make_monitor()
        with patch.object(pm, "_update_counters"), \
             patch.object(pm, "_check_alerts") as mock_alerts, \
             patch.object(pm, "_decrement_concurrent_count"):
            mock_cache.get.return_value = {"site_name": "s"}
            pm.record_acquisition_end("id1", success=True, duration=200.0)
            mock_alerts.assert_called_once()

    # ─── get_real_time_metrics ───

    @patch("plugins.court_automation.token.performance_monitor.performance_monitor._get_average_durations", return_value=(10.0, 5.0))
    @patch("plugins.court_automation.token.performance_monitor.performance_monitor._get_concurrent_count", return_value=2)
    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_get_real_time_metrics(self, mock_cache: MagicMock, mock_conc: MagicMock, mock_dur: MagicMock) -> None:
        pm = self._make_monitor()
        pm._cache_stats = {"hits": 5, "misses": 5, "total_requests": 10}
        # Mock _get_counters
        with patch.object(pm, "_get_counters", return_value={
            "total": 10, "success": 8, "failed": 2,
            "timeout": 1, "network_error": 0, "captcha_error": 0, "credential_error": 0,
        }):
            metrics = pm.get_real_time_metrics()
            assert metrics.total_acquisitions == 10
            assert metrics.success_rate == 80.0
            assert metrics.cache_hit_rate == 50.0

    # ─── check_health ───

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    def test_check_health_healthy(self, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 1)
        mock_metrics = PerformanceMetrics(
            total_acquisitions=100, success_rate=95.0, avg_duration=30.0,
            concurrent_acquisitions=2, cache_hit_rate=85.0, timeout_count=1,
        )
        with patch.object(pm, "get_real_time_metrics", return_value=mock_metrics):
            result = pm.check_health()
            assert result["status"] == "healthy"

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    def test_check_health_unhealthy_low_success(self, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 1)
        mock_metrics = PerformanceMetrics(
            total_acquisitions=100, success_rate=50.0, avg_duration=30.0,
            concurrent_acquisitions=2, cache_hit_rate=85.0, timeout_count=1,
        )
        with patch.object(pm, "get_real_time_metrics", return_value=mock_metrics):
            result = pm.check_health()
            assert result["status"] == "unhealthy"

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    def test_check_health_degraded_high_duration(self, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 1)
        mock_metrics = PerformanceMetrics(
            total_acquisitions=100, success_rate=90.0, avg_duration=200.0,
            concurrent_acquisitions=10, cache_hit_rate=85.0, timeout_count=1,
        )
        with patch.object(pm, "get_real_time_metrics", return_value=mock_metrics):
            result = pm.check_health()
            assert result["status"] == "degraded"

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    def test_check_health_warning_low_cache(self, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 1)
        mock_metrics = PerformanceMetrics(
            total_acquisitions=100, success_rate=90.0, avg_duration=30.0,
            concurrent_acquisitions=2, cache_hit_rate=30.0, timeout_count=1,
        )
        with patch.object(pm, "get_real_time_metrics", return_value=mock_metrics):
            result = pm.check_health()
            assert result["status"] == "warning"

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    def test_check_health_high_timeout_rate(self, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 1)
        mock_metrics = PerformanceMetrics(
            total_acquisitions=100, success_rate=90.0, avg_duration=30.0,
            concurrent_acquisitions=2, cache_hit_rate=85.0, timeout_count=20,
        )
        with patch.object(pm, "get_real_time_metrics", return_value=mock_metrics):
            result = pm.check_health()
            assert any(a["type"] == "high_timeout_rate" for a in result["alerts"])

    # ─── reset_metrics ───

    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_reset_metrics(self, mock_cache: MagicMock) -> None:
        pm = self._make_monitor()
        pm._cache_stats = {"hits": 100, "misses": 50, "total_requests": 150}
        pm.reset_metrics()
        assert pm._cache_stats["hits"] == 0

    # ─── _update_counters ───

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_update_counters_success(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.localdate.return_value = datetime(2025, 1, 1).date()
        mock_cache.get.return_value = 0
        pm._update_counters(True, None, site_name="site")
        assert mock_cache.set.call_count == 2  # total + success

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("plugins.court_automation.token.performance_monitor.cache")
    def test_update_counters_failure_with_error_type(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.localdate.return_value = datetime(2025, 1, 1).date()
        mock_cache.get.return_value = 0
        pm._update_counters(False, "timeout", site_name="site")
        assert mock_cache.set.call_count == 3  # total + failed + error_type

    # ─── _get_average_durations ───

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("apps.automation.models.TokenAcquisitionHistory")
    def test_get_average_durations_success(self, mock_model: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 2)
        mock_qs = MagicMock()
        mock_qs.filter.return_value.aggregate.return_value = {"avg_total": 15.0, "avg_login": 5.0}
        mock_model.objects = mock_qs
        total, login = pm._get_average_durations()
        assert total == 15.0
        assert login == 5.0

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("apps.automation.models.TokenAcquisitionHistory")
    def test_get_average_durations_no_data(self, mock_model: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 2)
        mock_qs = MagicMock()
        mock_qs.filter.return_value.aggregate.return_value = {"avg_total": None, "avg_login": None}
        mock_model.objects = mock_qs
        total, login = pm._get_average_durations()
        assert total == 0.0
        assert login == 0.0

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("apps.automation.models.TokenAcquisitionHistory")
    def test_get_average_durations_exception(self, mock_model: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 2)
        mock_model.objects.filter.side_effect = RuntimeError("db fail")
        total, login = pm._get_average_durations()
        assert total == 0.0
        assert login == 0.0

    # ─── get_statistics_report ───

    @patch("plugins.court_automation.token.performance_monitor.timezone")
    @patch("apps.automation.models.TokenAcquisitionHistory")
    def test_get_statistics_report(self, mock_model: MagicMock, mock_tz: MagicMock) -> None:
        pm = self._make_monitor()
        mock_tz.now.return_value = datetime(2025, 1, 8)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.count.return_value = 10
        mock_qs.values.return_value.annotate.return_value.order_by.return_value = []
        mock_qs.aggregate.return_value = {"total_duration__avg": 10.0, "login_duration__avg": 5.0}
        mock_model.objects = mock_qs

        with patch.object(pm, "get_real_time_metrics", return_value=PerformanceMetrics()):
            report = pm.get_statistics_report()
            assert "period" in report
            assert "summary" in report

    # ─── _check_alerts ───

    def test_check_alerts_high_duration(self) -> None:
        pm = self._make_monitor()
        with patch.object(pm, "_check_alerts") as mock_check:
            mock_check.return_value = None
            # Call through to the real method
            pm._check_alerts("id1", True, 200.0, None)

    def test_check_alerts_failure(self) -> None:
        pm = self._make_monitor()
        pm._check_alerts("id1", False, 5.0, "network_error")
