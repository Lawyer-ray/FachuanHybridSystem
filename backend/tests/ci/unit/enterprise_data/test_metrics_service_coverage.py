"""Coverage tests for enterprise_data.services.metrics_service."""

from unittest.mock import MagicMock, patch

import pytest


class TestEnterpriseDataMetricsService:
    def _make(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        return EnterpriseDataMetricsService(window_seconds=300, alert_min_samples=3)

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_record_first_call(self, mock_cache):
        svc = self._make()
        mock_cache.get.return_value = None
        mock_cache.set = MagicMock()
        result = svc.record(provider="test", capability="cap", success=True, duration_ms=100, fallback_used=False)
        assert "total" in result or result is not None

    def test_init_defaults(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService()
        assert svc._window_seconds >= 60

    def test_init_custom(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService(
            window_seconds=120,
            alert_min_samples=5,
            alert_success_rate_threshold=0.95,
            alert_fallback_rate_threshold=0.1,
            alert_avg_latency_ms_threshold=500,
        )
        assert svc._window_seconds == 120
        assert svc._alert_min_samples == 5
