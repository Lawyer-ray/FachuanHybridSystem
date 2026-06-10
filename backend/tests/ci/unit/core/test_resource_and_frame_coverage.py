"""Comprehensive tests for resource_monitor, frame_processing_service, and other coverage targets."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.infrastructure.resource_monitor import (
    ResourceMonitor,
    ResourceThresholds,
    ResourceUsage,
)


# ===========================================================================
# ResourceMonitor tests
# ===========================================================================
class TestResourceThresholds:
    def test_defaults(self):
        t = ResourceThresholds()
        assert t.memory_warning == 80.0
        assert t.memory_critical == 90.0
        assert t.cpu_warning == 80.0
        assert t.disk_warning == 85.0
        assert t.disk_critical == 95.0
        assert t.auto_restart_memory == 95.0


class TestResourceMonitorInit:
    @patch.dict(os.environ, {}, clear=False)
    def test_default_init(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon.thresholds.memory_warning == 80.0

    def test_get_bool_env_true(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon._get_bool_env("NONEXISTENT_BOOL_KEY", True) is True

    @patch.dict(os.environ, {"TEST_BOOL_KEY": "true"})
    def test_get_bool_env_from_env(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon._get_bool_env("TEST_BOOL_KEY", False) is True

    @patch.dict(os.environ, {"TEST_BOOL_KEY": "false"})
    def test_get_bool_env_false(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon._get_bool_env("TEST_BOOL_KEY", True) is False

    @patch.dict(os.environ, {"TEST_BOOL_KEY": "1"})
    def test_get_bool_env_one(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon._get_bool_env("TEST_BOOL_KEY", False) is True

    @patch.dict(os.environ, {"TEST_BOOL_KEY": "yes"})
    def test_get_bool_env_yes(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            assert mon._get_bool_env("TEST_BOOL_KEY", False) is True


class TestResourceMonitorHealth:
    def _make_mon(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            return mon

    def test_healthy(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=50.0,
            memory_used_mb=4000, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "healthy"

    def test_memory_warning(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=85.0,
            memory_used_mb=7000, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "warning"

    def test_memory_critical(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=95.0,
            memory_used_mb=7500, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "critical"

    def test_cpu_warning(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=85.0, memory_percent=50.0,
            memory_used_mb=4000, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "warning"

    def test_disk_warning(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=50.0,
            memory_used_mb=4000, memory_total_mb=8000,
            disk_percent=90.0, disk_used_gb=180, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "warning"

    def test_disk_critical(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=50.0,
            memory_used_mb=4000, memory_total_mb=8000,
            disk_percent=96.0, disk_used_gb=190, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.check_resource_health()
            assert result["status"] == "critical"

    def test_no_usage(self):
        mon = self._make_mon()
        with patch.object(mon, "get_current_usage", return_value=None):
            result = mon.check_resource_health()
            assert result["status"] == "unknown"


class TestResourceMonitorRestart:
    def _make_mon(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            return mon

    def test_disabled(self):
        mon = self._make_mon()
        mon.auto_restart_enabled = False
        should, msg = mon.should_trigger_restart()
        assert should is False

    def test_cooldown_active(self):
        mon = self._make_mon()
        mon._last_restart_time = datetime.now()
        should, msg = mon.should_trigger_restart()
        assert should is False
        assert "cooldown" in msg.lower() or "remaining" in msg.lower()

    def test_high_memory_triggers_restart(self):
        mon = self._make_mon()
        mon._last_restart_time = None
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=96.0,
            memory_used_mb=7500, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            should, msg = mon.should_trigger_restart()
            assert should is True

    def test_normal_memory_no_restart(self):
        mon = self._make_mon()
        mon._last_restart_time = None
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=50.0,
            memory_used_mb=4000, memory_total_mb=8000,
            disk_percent=60.0, disk_used_gb=100, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            should, msg = mon.should_trigger_restart()
            assert should is False

    def test_record_restart(self):
        mon = self._make_mon()
        mon.record_restart()
        assert mon._last_restart_time is not None


class TestResourceMonitorRecommendations:
    def _make_mon(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            return mon

    def test_low_usage(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=10.0, memory_percent=20.0,
            memory_used_mb=2000, memory_total_mb=8000,
            disk_percent=30.0, disk_used_gb=50, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.get_resource_recommendations()
            assert len(result["recommendations"]) >= 1

    def test_high_usage(self):
        mon = self._make_mon()
        usage = ResourceUsage(
            cpu_percent=90.0, memory_percent=90.0,
            memory_used_mb=7500, memory_total_mb=8000,
            disk_percent=90.0, disk_used_gb=180, disk_total_gb=200,
            timestamp=datetime.now(),
        )
        with patch.object(mon, "get_current_usage", return_value=usage):
            result = mon.get_resource_recommendations()
            assert len(result["recommendations"]) >= 2

    def test_no_usage(self):
        mon = self._make_mon()
        with patch.object(mon, "get_current_usage", return_value=None):
            result = mon.get_resource_recommendations()
            assert "message" in result


class TestResourceMonitorStartStop:
    def test_start_stop(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            mon.start_monitoring(interval=1)
            mon.stop_monitoring()

    def test_start_when_disabled(self):
        with patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True):
            mon = ResourceMonitor()
            mon.monitoring_enabled = False
            mon.start_monitoring()  # Should be no-op
            mon.stop_monitoring()


# ===========================================================================
# FrameProcessingService tests
# ===========================================================================
class TestFrameProcessingService:
    def _get_service(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService
        return FrameProcessingService()

    def test_collect_frame_files(self, tmp_path):
        svc = self._get_service()
        (tmp_path / "frame_001.jpg").write_bytes(b"jpg")
        (tmp_path / "frame_002.png").write_bytes(b"png")
        (tmp_path / "frame_003.txt").write_bytes(b"txt")
        files = svc.collect_frame_files(str(tmp_path))
        assert len(files) == 2
        assert all(f.endswith((".jpg", ".png")) for f in files)

    def test_collect_frame_files_empty(self, tmp_path):
        svc = self._get_service()
        files = svc.collect_frame_files(str(tmp_path))
        assert files == []

    def test_calc_capture_time_interval_based(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        from apps.chat_records.services.extraction.video_frame_extract_service import FFProbeInfo
        params = ExtractParams(interval_based=True, interval_seconds=2.0, strategy="interval",
                                dedup_threshold=10, ocr_similarity_threshold=0.9, ocr_min_new_chars=5)
        info = FFProbeInfo(duration_seconds=10.0, time_base_seconds=0.0)
        result = svc.calc_capture_time("frame_003.jpg", 3, params, info)
        assert result == 4.0  # (3-1) * 2.0

    def test_calc_capture_time_not_interval(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        from apps.chat_records.services.extraction.video_frame_extract_service import FFProbeInfo
        params = ExtractParams(interval_based=False, interval_seconds=0, strategy="keyframe",
                                dedup_threshold=10, ocr_similarity_threshold=0.9, ocr_min_new_chars=5)
        info = FFProbeInfo(duration_seconds=10.0, time_base_seconds=0.04)
        result = svc.calc_capture_time("frame_000042.jpg", 1, params, info)
        assert result == pytest.approx(42 * 0.04)

    def test_calc_capture_time_not_interval_no_match(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import ExtractParams
        from apps.chat_records.services.extraction.video_frame_extract_service import FFProbeInfo
        params = ExtractParams(interval_based=False, interval_seconds=0, strategy="keyframe",
                                dedup_threshold=10, ocr_similarity_threshold=0.9, ocr_min_new_chars=5)
        info = FFProbeInfo(duration_seconds=10.0, time_base_seconds=0.04)
        result = svc.calc_capture_time("frame_no_number.jpg", 1, params, info)
        assert result is None

    def test_is_dhash_duplicate(self):
        svc = self._get_service()
        mock_selection = MagicMock()
        mock_selection.hamming_distance_hex.return_value = 3
        kept = ["abc", "def", "ghi"]
        assert svc.is_dhash_duplicate(mock_selection, "xyz", kept, window=10, threshold=5) is True

    def test_is_dhash_not_duplicate(self):
        svc = self._get_service()
        mock_selection = MagicMock()
        mock_selection.hamming_distance_hex.return_value = 10
        kept = ["abc"]
        assert svc.is_dhash_duplicate(mock_selection, "xyz", kept, window=10, threshold=5) is False

    def test_is_pixel_duplicate(self):
        svc = self._get_service()
        mock_selection = MagicMock()
        mock_selection.mean_abs_diff.return_value = 0.01
        assert svc.is_pixel_duplicate(mock_selection, b"thumb", [b"prev"], window=5, threshold=0.05) is True

    def test_is_pixel_not_duplicate(self):
        svc = self._get_service()
        mock_selection = MagicMock()
        mock_selection.mean_abs_diff.return_value = 0.5
        assert svc.is_pixel_duplicate(mock_selection, b"thumb", [b"prev"], window=5, threshold=0.05) is False

    def test_check_ocr_similarity_empty_text(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import DedupState
        state = DedupState()
        result = svc.check_ocr_similarity("", state, 0.9, 5)
        assert result is None

    def test_check_ocr_similarity_no_kept_texts(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import DedupState
        state = DedupState()
        result = svc.check_ocr_similarity("some text", state, 0.9, 5)
        assert result is None

    def test_get_ocr_frame_score_empty(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import DedupState
        state = DedupState()
        score = svc.get_ocr_frame_score(0.0, "", state)
        assert score == 0.0

    def test_get_ocr_frame_score_no_kept(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import DedupState
        state = DedupState()
        score = svc.get_ocr_frame_score(0.0, "some text", state)
        assert score == 0.0

    def test_reorder_screenshots(self):
        svc = self._get_service()
        callback = MagicMock()
        svc.reorder_screenshots(42, callback)
        callback.assert_called_once_with(42)

    def test_is_frame_duplicate_sha_hit(self):
        svc = self._get_service()
        from apps.chat_records.services.extraction.extract_helpers import DedupState, ExtractParams
        state = DedupState()
        state.existing_sha256.add("existing_digest")
        params = ExtractParams(interval_based=True, interval_seconds=1, strategy="interval",
                                dedup_threshold=10, ocr_similarity_threshold=0.9, ocr_min_new_chars=5)
        mock_selection = MagicMock()
        is_dup, thumb = svc.is_frame_duplicate(
            b"content", "existing_digest", "dhash", state, params, mock_selection, 5, 0.0
        )
        assert is_dup is True
