"""Token 性能监控服务测试。"""

from __future__ import annotations

from apps.automation.services.token.performance_monitor import (
    PerformanceMetrics,
    AlertThresholds,
)


class TestPerformanceMetrics:
    """PerformanceMetrics 数据类测试。"""

    def test_default_values(self) -> None:
        metrics = PerformanceMetrics()
        assert metrics.total_acquisitions == 0
        assert metrics.successful_acquisitions == 0
        assert metrics.failed_acquisitions == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_duration == 0.0
        assert metrics.avg_login_duration == 0.0
        assert metrics.timeout_count == 0
        assert metrics.network_error_count == 0
        assert metrics.captcha_error_count == 0
        assert metrics.credential_error_count == 0
        assert metrics.concurrent_acquisitions == 0
        assert metrics.cache_hit_rate == 0.0

    def test_to_dict(self) -> None:
        metrics = PerformanceMetrics(total_acquisitions=10, successful_acquisitions=8)
        d = metrics.to_dict()
        assert d["total_acquisitions"] == 10
        assert d["successful_acquisitions"] == 8
        assert "success_rate" in d


class TestAlertThresholds:
    """AlertThresholds 数据类测试。"""

    def test_default_values(self) -> None:
        thresholds = AlertThresholds()
        assert thresholds.min_success_rate == 80.0
        assert thresholds.max_avg_duration == 120.0
        assert thresholds.max_timeout_rate == 10.0
        assert thresholds.max_concurrent_acquisitions == 5
        assert thresholds.min_cache_hit_rate == 70.0

    def test_custom_values(self) -> None:
        thresholds = AlertThresholds(min_success_rate=90.0, max_avg_duration=60.0)
        assert thresholds.min_success_rate == 90.0
        assert thresholds.max_avg_duration == 60.0
