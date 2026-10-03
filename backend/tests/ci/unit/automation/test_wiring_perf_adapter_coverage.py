"""Coverage tests for automation.services.wiring and automation.services.token.performance_monitor_service_adapter."""

from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestAutomationWiring:
    @patch("apps.automation.services.wiring.ServiceLocator")
    def test_wiring_functions(self, mock_sl):
        from apps.automation.services.wiring import get_baoquan_token_service, get_case_service, get_llm_service

        mock_sl.get_case_service.return_value = "case_svc"
        mock_sl.get_llm_service.return_value = "llm_svc"
        mock_sl.get_baoquan_token_service.return_value = "baoquan_svc"

        assert get_case_service() == "case_svc"
        assert get_llm_service() == "llm_svc"
        assert get_baoquan_token_service() == "baoquan_svc"


class TestPerformanceMonitorServiceAdapter:
    @patch("psutil.cpu_percent", return_value=50.0)
    @patch("psutil.cpu_count", return_value=4)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.pids", return_value=[1, 2, 3])
    @patch("psutil.getloadavg", return_value=(1.0, 2.0, 3.0))
    @patch("apps.automation.utils.logging.AutomationLogger")
    @patch("django.utils.timezone.now")
    def test_get_system_metrics(
        self, mock_now, mock_logger, mock_load, mock_pids,
        mock_net, mock_disk, mock_mem, mock_cpu_count, mock_cpu_pct,
    ):
        from plugins.court_automation.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        mock_now.return_value = MagicMock(isoformat=lambda: "2024-01-01")
        mock_mem.return_value = MagicMock(total=8e9, available=4e9, used=4e9, percent=50.0)
        mock_disk.return_value = MagicMock(total=100e9, used=60e9, free=40e9)
        mock_net.return_value = MagicMock(bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20)

        adapter = PerformanceMonitorServiceAdapter()
        metrics = adapter.get_system_metrics()
        assert "cpu" in metrics
        assert "memory" in metrics

    @pytest.mark.django_db
    def test_get_token_acquisition_metrics(self):
        from plugins.court_automation.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        with patch("apps.automation.models.TokenAcquisitionHistory") as mock_history:
            mock_qs = MagicMock()
            mock_qs.count.return_value = 0
            mock_qs.filter.return_value.count.return_value = 0
            mock_qs.exclude.return_value.count.return_value = 0
            mock_qs.values.return_value.annotate.return_value = []
            mock_qs.filter.return_value.aggregate.return_value = {"avg_duration": None}
            mock_history.objects.filter.return_value = mock_qs

            adapter = PerformanceMonitorServiceAdapter()
            metrics = adapter.get_token_acquisition_metrics(hours=24)
            assert "overall" in metrics
            assert metrics["overall"]["total_attempts"] == 0

    def test_get_api_performance_metrics(self):
        from plugins.court_automation.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        with patch("django.utils.timezone.now", return_value=MagicMock(isoformat=lambda: "2024-01-01")):
            adapter = PerformanceMonitorServiceAdapter()
            metrics = adapter.get_api_performance_metrics()
            assert "metrics" in metrics

    def test_record_performance_metric(self):
        from plugins.court_automation.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        adapter = PerformanceMonitorServiceAdapter()
        adapter.record_performance_metric("test_metric", 42.0, {"tag": "value"})
