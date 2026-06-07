"""Coverage tests for core.infrastructure.health._resources."""

from unittest.mock import MagicMock, patch

import pytest


class TestEvaluateResourceStatus:
    def test_healthy(self):
        from apps.core.infrastructure.health._resources import _evaluate_resource_status
        from apps.core.infrastructure.health._models import HealthStatus

        status, issues = _evaluate_resource_status(50.0, 50.0, None, 4)
        assert status == HealthStatus.HEALTHY
        assert issues == []

    def test_high_cpu(self):
        from apps.core.infrastructure.health._resources import _evaluate_resource_status
        from apps.core.infrastructure.health._models import HealthStatus

        status, issues = _evaluate_resource_status(95.0, 50.0, None, 4)
        assert status == HealthStatus.DEGRADED
        assert any("CPU" in i for i in issues)

    def test_high_memory(self):
        from apps.core.infrastructure.health._resources import _evaluate_resource_status
        from apps.core.infrastructure.health._models import HealthStatus

        status, issues = _evaluate_resource_status(50.0, 95.0, None, 4)
        assert status == HealthStatus.UNHEALTHY

    def test_elevated_memory(self):
        from apps.core.infrastructure.health._resources import _evaluate_resource_status
        from apps.core.infrastructure.health._models import HealthStatus

        status, issues = _evaluate_resource_status(50.0, 85.0, None, 4)
        assert status == HealthStatus.DEGRADED

    def test_high_load(self):
        from apps.core.infrastructure.health._resources import _evaluate_resource_status
        from apps.core.infrastructure.health._models import HealthStatus

        status, issues = _evaluate_resource_status(50.0, 50.0, (20.0, 15.0, 10.0), 4)
        assert status == HealthStatus.DEGRADED
        assert any("load" in i.lower() for i in issues)


class TestCheckSystemResources:
    @patch("apps.core.infrastructure.health._resources.RESOURCE_MONITOR_AVAILABLE", False)
    @patch("apps.core.infrastructure.health._resources._check_via_psutil")
    def test_check_system_resources_fallback(self, mock_psutil):
        from apps.core.infrastructure.health._resources import check_system_resources

        mock_psutil.return_value = MagicMock()
        result = check_system_resources()
        assert result is not None

    @patch("apps.core.infrastructure.health._resources.RESOURCE_MONITOR_AVAILABLE", False)
    @patch("apps.core.infrastructure.health._resources._check_via_psutil")
    def test_check_system_resources_error(self, mock_psutil):
        from apps.core.infrastructure.health._resources import check_system_resources
        from apps.core.infrastructure.health._models import HealthStatus

        mock_psutil.side_effect = Exception("psutil error")
        result = check_system_resources()
        assert result.status == HealthStatus.DEGRADED


class TestCheckViaPsutil:
    @patch("apps.core.infrastructure.health._resources.psutil")
    @patch("apps.core.infrastructure.health._resources.os")
    def test_check_via_psutil(self, mock_os, mock_psutil):
        from apps.core.infrastructure.health._resources import _check_via_psutil

        mock_psutil.cpu_percent.return_value = 30.0
        mock_psutil.cpu_count.return_value = 4
        mock_mem = MagicMock()
        mock_mem.total = 8e9
        mock_mem.available = 4e9
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_proc = MagicMock()
        mock_proc.pid = 1
        mock_proc.cpu_percent.return_value = 5.0
        mock_proc.memory_percent.return_value = 10.0
        mock_proc.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)
        mock_proc.num_threads.return_value = 10
        mock_proc.create_time.return_value = 100000
        mock_psutil.Process.return_value = mock_proc
        mock_os.getloadavg.return_value = (1.0, 2.0, 3.0)

        result = _check_via_psutil({})
        assert result is not None
