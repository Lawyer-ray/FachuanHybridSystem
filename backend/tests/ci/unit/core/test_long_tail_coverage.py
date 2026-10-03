"""Long-tail coverage tests for multiple core modules."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# tests for apps.core.tasking.runtime (41 missing)
# ---------------------------------------------------------------------------

class TestTaskRunContext:
    def test_from_django_q_default_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext.from_django_q()
        assert ctx.timeout_seconds == 600.0
        assert ctx.soft_deadline_monotonic > ctx.started_monotonic

    def test_from_django_q_explicit_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext.from_django_q(timeout_seconds=120)
        assert ctx.timeout_seconds == 120.0

    def test_from_django_q_invalid_q_cluster_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        with patch("apps.core.tasking.runtime.settings") as mock_settings:
            mock_settings.Q_CLUSTER = {"timeout": "bad"}
            ctx = TaskRunContext.from_django_q()
            assert ctx.timeout_seconds == 600.0

    def test_from_django_q_q_cluster_value_error(self):
        from apps.core.tasking.runtime import TaskRunContext

        with patch("apps.core.tasking.runtime.settings") as mock_settings:
            mock_settings.Q_CLUSTER = {"timeout": None}
            ctx = TaskRunContext.from_django_q()
            assert ctx.timeout_seconds == 600.0

    def test_is_past_soft_deadline_false(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext.from_django_q(timeout_seconds=999999)
        assert ctx.is_past_soft_deadline() is False

    def test_is_past_soft_deadline_true(self):
        import time as _time

        from apps.core.tasking.runtime import TaskRunContext

        now = _time.monotonic()
        ctx = TaskRunContext(
            started_monotonic=now,
            soft_deadline_monotonic=now - 100,
            timeout_seconds=10,
        )
        assert ctx.is_past_soft_deadline() is True

class TestCancellationToken:
    def test_not_cancelled(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: False)
        assert token.is_cancelled() is False

    def test_cancelled(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: True)
        assert token.is_cancelled() is True

    def test_raises_type_error_returns_false(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: None.bad_attr)
        assert token.is_cancelled() is False

class TestProgressReporter:
    def test_report_basic(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=0,
        )
        reporter.report(current=5, total=10, message="halfway", force=True)
        assert len(updates) == 1
        assert updates[0][0] == 50

    def test_report_throttled(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=999,
        )
        reporter.report(current=1, total=10, message="a", force=True)
        reporter.report(current=2, total=10, message="b", force=False)
        assert len(updates) == 1

    def test_report_zero_total(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=0,
        )
        reporter.report(current=0, total=0, message="empty", force=True)
        assert updates[0][0] == 0

    def test_report_same_progress_within_interval_skips(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=999,
        )
        reporter.report(current=5, total=10, message="same", force=True)
        reporter.report(current=5, total=10, message="same", force=False)
        assert len(updates) == 1

    def test_report_same_progress_different_message_within_interval_skips(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=999,
        )
        reporter.report(current=5, total=10, message="a", force=True)
        reporter.report(current=5, total=10, message="b", force=False)
        # different message but within interval => skipped
        assert len(updates) == 1

    def test_report_extra(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=0,
        )
        reporter.report_extra(progress=99, current=50, total=100, message="extra", force=True)
        assert updates[0] == (99, 50, 100, "extra")

    def test_report_extra_throttled(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=999,
        )
        reporter.report_extra(progress=50, current=1, total=2, message="a", force=True)
        reporter.report_extra(progress=75, current=2, total=3, message="b", force=False)
        assert len(updates) == 1

    def test_report_overflow_clamped(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=0,
        )
        reporter.report(current=200, total=100, message="over", force=True)
        assert updates[0][0] == 100

    def test_report_negative_clamped(self):
        from apps.core.tasking.runtime import ProgressReporter

        updates: list[tuple] = []
        reporter = ProgressReporter(
            update_fn=lambda p, c, t, m: updates.append((p, c, t, m)),
            min_interval_seconds=0,
        )
        reporter.report(current=-10, total=100, message="neg", force=True)
        assert updates[0][0] == 0

# ---------------------------------------------------------------------------
# tests for apps.core.tasking.cleanup_tasks (36 missing)
# ---------------------------------------------------------------------------

class TestCleanupTasks:
    def test_cleanup_temp_files_no_dir(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import cleanup_temp_files

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = cleanup_temp_files()
            assert result["skipped"] is True
            assert result["removed"] == 0

    def test_cleanup_temp_files_removes_old(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        old_file = tmp_dir / "old.txt"
        old_file.write_text("old")
        import os

        os.utime(old_file, (0, 0))  # set mtime to epoch

        new_file = tmp_dir / "new.txt"
        new_file.write_text("new")

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = cleanup_temp_files(max_age_hours=1)
            assert result["removed"] >= 1
            assert new_file.exists()

    def test_cleanup_temp_files_oserror(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        old_file = tmp_dir / "old.txt"
        old_file.write_text("old")
        import os

        os.utime(old_file, (0, 0))

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            with patch("pathlib.Path.unlink", side_effect=OSError("no")):
                result = cleanup_temp_files(max_age_hours=1)
                assert result["failed"] >= 1

    def test_cleanup_export_files_no_dir(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import cleanup_export_files

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = cleanup_export_files()
            assert result["skipped"] is True

    def test_cleanup_export_files_removes_old(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import cleanup_export_files

        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        old_file = exports_dir / "old.csv"
        old_file.write_text("data")
        import os

        os.utime(old_file, (0, 0))

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = cleanup_export_files(max_age_days=1)
            assert result["removed"] >= 1

    def test_check_disk_space_ok(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import check_disk_space

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = check_disk_space(warning_pct=99.0, critical_pct=100.0)
            assert result["status"] == "ok"

    def test_check_disk_space_oserror(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import check_disk_space

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            with patch("os.statvfs", side_effect=OSError("no")):
                result = check_disk_space()
                assert result["status"] == "error"

    def test_check_disk_space_warning(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import check_disk_space

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            mock_stat = MagicMock()
            mock_stat.f_blocks = 1000
            mock_stat.f_frsize = 1024 * 1024
            mock_stat.f_bavail = 100  # ~90% used
            with patch("os.statvfs", return_value=mock_stat):
                result = check_disk_space(warning_pct=80.0, critical_pct=95.0)
                assert result["status"] == "warning"

    def test_check_disk_space_critical(self, tmp_path):
        from apps.core.tasking.cleanup_tasks import check_disk_space

        with patch("apps.core.tasking.cleanup_tasks.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            mock_stat = MagicMock()
            mock_stat.f_blocks = 1000
            mock_stat.f_frsize = 1024 * 1024
            mock_stat.f_bavail = 10  # ~99% used
            with patch("os.statvfs", return_value=mock_stat):
                result = check_disk_space(warning_pct=80.0, critical_pct=95.0)
                assert result["status"] == "critical"

# ---------------------------------------------------------------------------
# tests for apps.core.infrastructure.resource_monitor (36 missing)
# ---------------------------------------------------------------------------

class TestResourceMonitor:
    def test_init_no_psutil(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", False):
            from apps.core.infrastructure.resource_monitor import ResourceMonitor

            monitor = ResourceMonitor()
            assert monitor.monitoring_enabled is False

    def test_get_current_usage_no_psutil(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", False):
            from apps.core.infrastructure.resource_monitor import ResourceMonitor

            monitor = ResourceMonitor()
            assert monitor.get_current_usage() is None

    def test_check_resource_health_no_usage(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        with patch.object(monitor, "get_current_usage", return_value=None):
            result = monitor.check_resource_health()
            assert result["status"] == "unknown"

    def test_check_resource_health_healthy(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=30,
            memory_used_mb=1000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "healthy"

    def test_check_resource_health_warning_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=85,
            memory_used_mb=5000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_critical_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=95,
            memory_used_mb=7000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "critical"

    def test_check_resource_health_warning_cpu(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=85,
            memory_percent=50,
            memory_used_mb=3000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_warning_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=30,
            memory_used_mb=1000,
            memory_total_mb=8000,
            disk_percent=90,
            disk_used_gb=400,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_critical_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=30,
            memory_used_mb=1000,
            memory_total_mb=8000,
            disk_percent=97,
            disk_used_gb=490,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "critical"

    def test_should_trigger_restart_disabled(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = False
        should, reason = monitor.should_trigger_restart()
        assert should is False
        assert "disabled" in reason.lower()

    def test_should_trigger_restart_cooldown(self):
        from django.utils import timezone

        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        # 与 should_trigger_restart 内部一致使用 aware datetime（USE_TZ=True 下 naive 比较会 TypeError）
        monitor._last_restart_time = timezone.now()
        should, reason = monitor.should_trigger_restart()
        assert should is False
        assert "cooldown" in reason.lower()

    def test_should_trigger_restart_no_usage(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        with patch.object(monitor, "get_current_usage", return_value=None):
            should, reason = monitor.should_trigger_restart()
            assert should is False
            assert "unavailable" in reason.lower()

    def test_should_trigger_restart_high_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=98,
            memory_used_mb=7000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            should, reason = monitor.should_trigger_restart()
            assert should is True

    def test_should_trigger_restart_ok(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=50,
            memory_used_mb=4000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            should, reason = monitor.should_trigger_restart()
            assert should is False
            assert "within" in reason.lower()

    def test_get_resource_recommendations_no_usage(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        with patch.object(monitor, "get_current_usage", return_value=None):
            result = monitor.get_resource_recommendations()
            assert "unavailable" in result["message"].lower()

    def test_get_resource_recommendations_low_cpu(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10,
            memory_percent=50,
            memory_used_mb=4000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("CPU" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_cpu(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=90,
            memory_percent=50,
            memory_used_mb=4000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("CPU" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50,
            memory_percent=50,
            memory_used_mb=4000,
            memory_total_mb=8000,
            disk_percent=90,
            disk_used_gb=400,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Disk" in r for r in result["recommendations"])

    def test_get_resource_recommendations_low_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50,
            memory_percent=30,
            memory_used_mb=2000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Memory" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50,
            memory_percent=85,
            memory_used_mb=6000,
            memory_total_mb=8000,
            disk_percent=50,
            disk_used_gb=100,
            disk_total_gb=500,
            timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Memory" in r for r in result["recommendations"])

    def test_get_bool_env(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor._get_bool_env("NONEXISTENT_KEY", True) is True
        assert monitor._get_bool_env("NONEXISTENT_KEY", False) is False

# ---------------------------------------------------------------------------
