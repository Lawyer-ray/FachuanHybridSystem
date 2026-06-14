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
        from apps.core.tasking.runtime import TaskRunContext

        import time as _time

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
            cpu_percent=10, memory_percent=30, memory_used_mb=1000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "healthy"

    def test_check_resource_health_warning_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10, memory_percent=85, memory_used_mb=5000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_critical_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10, memory_percent=95, memory_used_mb=7000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "critical"

    def test_check_resource_health_warning_cpu(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=85, memory_percent=50, memory_used_mb=3000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_warning_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10, memory_percent=30, memory_used_mb=1000,
            memory_total_mb=8000, disk_percent=90, disk_used_gb=400,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "warning"

    def test_check_resource_health_critical_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=10, memory_percent=30, memory_used_mb=1000,
            memory_total_mb=8000, disk_percent=97, disk_used_gb=490,
            disk_total_gb=500, timestamp=datetime.now(),
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
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        monitor._last_restart_time = datetime.now()
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
            cpu_percent=10, memory_percent=98, memory_used_mb=7000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            should, reason = monitor.should_trigger_restart()
            assert should is True

    def test_should_trigger_restart_ok(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = True
        usage = ResourceUsage(
            cpu_percent=10, memory_percent=50, memory_used_mb=4000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            should, reason = monitor.should_trigger_restart()
            assert should is False
            assert "within" in reason.lower()

    def test_record_restart(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.record_restart()
        assert monitor._last_restart_time is not None

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
            cpu_percent=10, memory_percent=50, memory_used_mb=4000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("CPU" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_cpu(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=90, memory_percent=50, memory_used_mb=4000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("CPU" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_disk(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50, memory_percent=50, memory_used_mb=4000,
            memory_total_mb=8000, disk_percent=90, disk_used_gb=400,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Disk" in r for r in result["recommendations"])

    def test_get_resource_recommendations_low_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50, memory_percent=30, memory_used_mb=2000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Memory" in r for r in result["recommendations"])

    def test_get_resource_recommendations_high_memory(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=50, memory_percent=85, memory_used_mb=6000,
            memory_total_mb=8000, disk_percent=50, disk_used_gb=100,
            disk_total_gb=500, timestamp=datetime.now(),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.get_resource_recommendations()
            assert any("Memory" in r for r in result["recommendations"])

    def test_start_monitoring_disabled(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.monitoring_enabled = False
        monitor.start_monitoring()  # should be a no-op

    def test_start_and_stop_monitoring(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.monitoring_enabled = True
        # Mock check_resource_health to avoid real system calls
        with patch.object(monitor, "check_resource_health", return_value={"status": "healthy", "message": ""}):
            with patch.object(monitor, "should_trigger_restart", return_value=(False, "")):
                monitor.start_monitoring(interval=1)
                assert monitor._monitoring_thread is not None
                assert monitor._monitoring_thread.is_alive()
                monitor.stop_monitoring()
                assert not monitor._monitoring_thread.is_alive()

    def test_start_monitoring_already_running(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.monitoring_enabled = True
        monitor._monitoring_thread = MagicMock()
        monitor._monitoring_thread.is_alive.return_value = True
        monitor.start_monitoring()  # should warn and return

    def test_monitoring_loop_handles_exceptions(self):
        """_monitoring_loop should continue on exception."""
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.monitoring_enabled = True
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("test error")
            return {"status": "healthy", "message": ""}

        with patch.object(monitor, "check_resource_health", side_effect=side_effect):
            with patch.object(monitor, "should_trigger_restart", return_value=(False, "")):
                monitor.start_monitoring(interval=0)
                import time as _time
                _time.sleep(0.1)
                monitor.stop_monitoring()

    def test_get_bool_env(self):
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor._get_bool_env("NONEXISTENT_KEY", True) is True
        assert monitor._get_bool_env("NONEXISTENT_KEY", False) is False


# ---------------------------------------------------------------------------
# tests for apps.automation.utils.logging_mixins.common (36 missing)
# ---------------------------------------------------------------------------


class TestLoggingMixinsCommon:
    def test_get_logger(self):
        from apps.automation.utils.logging_mixins.common import get_logger

        with patch("importlib.import_module") as mock_import:
            mock_mod = MagicMock()
            mock_mod.logger = MagicMock()
            mock_import.return_value = mock_mod
            result = get_logger()
            assert result == mock_mod.logger

    def test_utc_now_iso(self):
        from apps.automation.utils.logging_mixins.common import utc_now_iso

        with patch("apps.core.telemetry.time.utc_now_iso", return_value="2024-01-01T00:00:00Z"):
            result = utc_now_iso()
            assert result == "2024-01-01T00:00:00Z"

    def test_stable_hash_basic(self):
        from apps.automation.utils.logging_mixins.common import stable_hash

        with patch("django.conf.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            h1 = stable_hash("hello")
            h2 = stable_hash("hello")
            assert h1 == h2
            assert len(h1) == 32

    def test_stable_hash_empty(self):
        from apps.automation.utils.logging_mixins.common import stable_hash

        with patch("django.conf.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            h = stable_hash("")
            assert len(h) == 32

    def test_stable_hash_none_secret(self):
        from apps.automation.utils.logging_mixins.common import stable_hash

        with patch("django.conf.settings") as mock_settings:
            mock_settings.SECRET_KEY = None
            h = stable_hash("test")
            assert len(h) == 32

    def test_mask_account_email(self):
        from apps.automation.utils.logging_mixins.common import mask_account

        assert mask_account("test@example.com") == "t***t@example.com"
        assert mask_account("ab@example.com") == "a*@example.com"
        assert mask_account("a@example.com") == "*@example.com"

    def test_mask_account_short_email(self):
        from apps.automation.utils.logging_mixins.common import mask_account

        result = mask_account("ab@x.com")
        assert result.startswith("a*@x.com")

    def test_mask_account_phone(self):
        from apps.automation.utils.logging_mixins.common import mask_account

        result = mask_account("13800138000", keep_last=4)
        assert result.endswith("8000")
        assert result.startswith("***")

    def test_mask_account_empty(self):
        from apps.automation.utils.logging_mixins.common import mask_account

        assert mask_account("") == ""
        assert mask_account("  ") == ""

    def test_mask_account_keep_zero(self):
        from apps.automation.utils.logging_mixins.common import mask_account

        result = mask_account("abc", keep_last=0)
        assert result == "***"

    def test_sanitize_url_basic(self):
        from apps.automation.utils.logging_mixins.common import sanitize_url

        result = sanitize_url("https://example.com/path?a=1")
        assert result == "https://example.com/path"

    def test_sanitize_url_empty(self):
        from apps.automation.utils.logging_mixins.common import sanitize_url

        assert sanitize_url("") == ""

    def test_sanitize_url_truncated(self):
        from apps.automation.utils.logging_mixins.common import sanitize_url

        long_url = "https://example.com/" + "a" * 300
        result = sanitize_url(long_url, max_length=50)
        assert result.endswith("...")
        assert len(result) == 53  # 50 + "..."

    def test_normalize_cache_key_component_empty(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        assert normalize_cache_key_component("") == "empty"
        assert normalize_cache_key_component("  ") == "empty"

    def test_normalize_cache_key_component_simple(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        assert normalize_cache_key_component("hello-world") == "hello-world"

    def test_normalize_cache_key_component_uppercase(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        # "Hello" lowered to "hello" matches [a-z0-9._-]+ => returned as-is
        result = normalize_cache_key_component("Hello")
        assert result == "hello"

    def test_normalize_cache_key_component_special_chars(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        result = normalize_cache_key_component("hello world!")
        assert "hello" in result
        # Should have hash appended
        assert len(result) > 10

    def test_normalize_cache_key_component_too_long(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        result = normalize_cache_key_component("a" * 100, max_len=10)
        assert len(result) <= 50  # trimmed + hash

    def test_normalize_cache_key_component_all_special(self):
        from apps.automation.utils.logging_mixins.common import normalize_cache_key_component

        result = normalize_cache_key_component("!!!")
        # cleaned becomes 'x' + hash
        assert result.startswith("x-")


# ---------------------------------------------------------------------------
# tests for apps.core.config.steering._perf_monitor (36 missing)
# ---------------------------------------------------------------------------


class TestSteeringPerformanceMonitor:
    def _make_monitor(self, enabled=True):
        from apps.core.config.steering._perf_monitor import SteeringPerformanceMonitor

        return SteeringPerformanceMonitor({"enabled": enabled, "max_history_size": 10})

    def test_disabled_monitor(self):
        monitor = self._make_monitor(enabled=False)
        assert monitor.enabled is False

    def test_monitor_loading_disabled(self):
        monitor = self._make_monitor(enabled=False)
        result = monitor.monitor_loading("test.py", lambda: 42)
        assert result == 42

    def test_monitor_loading_success(self):
        monitor = self._make_monitor()
        result = monitor.monitor_loading("test.py", lambda: "ok")
        assert result == "ok"

    def test_monitor_loading_failure(self):
        monitor = self._make_monitor()
        with pytest.raises(ValueError, match="boom"):
            monitor.monitor_loading("test.py", lambda: (_ for _ in ()).throw(ValueError("boom")))

    def test_monitor_cached_loading_disabled(self):
        monitor = self._make_monitor(enabled=False)
        result = monitor.monitor_cached_loading("test.py", lambda: 99, cache_hit=True)
        assert result == 99

    def test_monitor_cached_loading_cache_hit(self):
        monitor = self._make_monitor()
        result = monitor.monitor_cached_loading("test.py", lambda: "cached", cache_hit=True)
        assert result == "cached"

    def test_monitor_cached_loading_failure(self):
        monitor = self._make_monitor()

        def bad():
            raise RuntimeError("cache load failed")

        with pytest.raises(RuntimeError, match="cache load failed"):
            monitor.monitor_cached_loading("test.py", bad, cache_hit=False)

    def test_check_performance_thresholds_all_levels(self):
        from apps.core.config.steering._perf_models import AlertLevel, LoadingPerformanceData

        monitor = self._make_monitor()
        alerts: list = []
        monitor.add_alert_callback(lambda a: alerts.append(a))

        def _make_data(**kwargs):
            defaults = {
                "spec_path": "test.py", "start_time": 0.0, "end_time": 0.0,
                "duration_ms": 0, "success": True, "cache_hit": False, "memory_usage_mb": 0.0,
            }
            defaults.update(kwargs)
            return LoadingPerformanceData(**defaults)

        # WARNING level
        monitor._check_performance_thresholds(_make_data(
            duration_ms=monitor.thresholds.load_time_warning_ms + 10,
        ))
        assert any(a.level == AlertLevel.WARNING for a in alerts)

        # ERROR level
        alerts.clear()
        monitor._check_performance_thresholds(_make_data(
            duration_ms=monitor.thresholds.load_time_error_ms + 10,
        ))
        assert any(a.level == AlertLevel.ERROR for a in alerts)

        # CRITICAL level
        alerts.clear()
        monitor._check_performance_thresholds(_make_data(
            duration_ms=monitor.thresholds.load_time_critical_ms + 10,
        ))
        assert any(a.level == AlertLevel.CRITICAL for a in alerts)

        # CRITICAL memory
        alerts.clear()
        monitor._check_performance_thresholds(_make_data(
            memory_usage_mb=monitor.thresholds.memory_usage_critical_mb + 100,
        ))
        assert any(a.level == AlertLevel.CRITICAL for a in alerts)

    def test_trigger_alert_callback_error(self):
        from apps.core.config.steering._perf_models import AlertLevel, PerformanceAlert

        monitor = self._make_monitor()

        def bad_callback(alert):
            raise RuntimeError("bad")

        monitor.add_alert_callback(bad_callback)
        alert = PerformanceAlert(
            level=AlertLevel.WARNING,
            message="test",
            metric_name="test",
            threshold=0,
            actual_value=0,
            timestamp=0,
        )
        monitor._trigger_alert(alert)  # should not raise

    def test_get_performance_report_disabled(self):
        monitor = self._make_monitor(enabled=False)
        assert monitor.get_performance_report() == {"enabled": False}

    def test_get_performance_report_enabled(self):
        monitor = self._make_monitor()
        report = monitor.get_performance_report()
        assert report["enabled"] is True
        assert "statistics" in report
        assert "analysis" in report

    def test_export_performance_data_disabled(self):
        monitor = self._make_monitor(enabled=False)
        monitor.export_performance_data("/tmp/test.json")  # no-op

    def test_export_performance_data_success(self, tmp_path):
        import json

        monitor = self._make_monitor()
        path = str(tmp_path / "report.json")
        monitor.export_performance_data(path)
        data = json.loads(path and open(path).read())
        assert data["enabled"] is True

    def test_export_performance_data_oserror(self, tmp_path):
        monitor = self._make_monitor()
        monitor.export_performance_data("/nonexistent/dir/report.json")  # should not raise

    def test_shutdown(self):
        monitor = self._make_monitor()
        monitor.shutdown()

    def test_shutdown_disabled(self):
        monitor = self._make_monitor(enabled=False)
        monitor.shutdown()

    def test_create_performance_monitor_from_config(self):
        from apps.core.config.steering._perf_monitor import create_performance_monitor_from_config

        monitor = create_performance_monitor_from_config({"enabled": False})
        assert monitor.enabled is False
