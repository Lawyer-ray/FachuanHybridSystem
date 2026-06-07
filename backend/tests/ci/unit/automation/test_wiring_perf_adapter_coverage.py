"""Coverage tests for automation.services.wiring and automation.services.token.performance_monitor_service_adapter."""

from unittest.mock import MagicMock, patch

import pytest


class TestAutomationWiring:
    @patch("apps.automation.services.wiring.ServiceLocator")
    def test_wiring_functions(self, mock_sl):
        from apps.automation.services.wiring import (
            get_case_service, get_organization_service, get_system_config_service,
            get_document_service, get_auto_namer_service, get_llm_service,
            get_token_service, get_task_service, get_browser_service,
            get_security_service, get_monitor_service,
        )

        mock_sl.get_case_service.return_value = "case_svc"
        mock_sl.get_organization_service.return_value = "org_svc"
        mock_sl.get_system_config_service.return_value = "config_svc"
        mock_sl.get_document_service.return_value = "doc_svc"
        mock_sl.get_auto_namer_service.return_value = "namer_svc"
        mock_sl.get_llm_service.return_value = "llm_svc"
        mock_sl.get_token_service.return_value = "token_svc"
        mock_sl.get_task_service.return_value = "task_svc"
        mock_sl.get_browser_service.return_value = "browser_svc"
        mock_sl.get_security_service.return_value = "sec_svc"
        mock_sl.get_monitor_service.return_value = "monitor_svc"

        assert get_case_service() == "case_svc"
        assert get_organization_service() == "org_svc"
        assert get_system_config_service() == "config_svc"
        assert get_document_service() == "doc_svc"
        assert get_auto_namer_service() == "namer_svc"
        assert get_llm_service() == "llm_svc"
        assert get_token_service() == "token_svc"
        assert get_task_service() == "task_svc"
        assert get_browser_service() == "browser_svc"
        assert get_security_service() == "sec_svc"
        assert get_monitor_service() == "monitor_svc"


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
        from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

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
        from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        adapter = PerformanceMonitorServiceAdapter()
        # Model may not exist in test DB, should return fallback metrics
        metrics = adapter.get_token_acquisition_metrics(hours=24)
        assert "overall" in metrics
        assert metrics["overall"]["total_attempts"] == 0

    def test_get_api_performance_metrics(self):
        from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        with patch("django.utils.timezone.now", return_value=MagicMock(isoformat=lambda: "2024-01-01")):
            adapter = PerformanceMonitorServiceAdapter()
            metrics = adapter.get_api_performance_metrics()
            assert "metrics" in metrics

    def test_record_performance_metric(self):
        from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

        adapter = PerformanceMonitorServiceAdapter()
        adapter.record_performance_metric("test_metric", 42.0, {"tag": "value"})
