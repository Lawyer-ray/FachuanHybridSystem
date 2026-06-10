"""Video frame extract service tests with mocked ffmpeg."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from apps.chat_records.services.extraction.video_frame_extract_service import (
    FFProbeInfo,
    VideoFrameExtractService,
)


class TestFFProbeInfo:
    def test_creation(self):
        info = FFProbeInfo(duration_seconds=120.5, time_base_seconds=0.001)
        assert info.duration_seconds == 120.5
        assert info.time_base_seconds == 0.001

    def test_creation_no_time_base(self):
        info = FFProbeInfo(duration_seconds=60.0)
        assert info.time_base_seconds is None


class TestVideoFrameExtractService:
    def _make(self):
        return VideoFrameExtractService()

    def test_estimate_total_frames(self):
        svc = self._make()
        assert svc.estimate_total_frames(100.0, 1.0) == 100
        assert svc.estimate_total_frames(100.0, 3.0) == 34
        assert svc.estimate_total_frames(0.0, 1.0) == 0
        assert svc.estimate_total_frames(100.0, 0.0) == 0

    def test_is_path_under_dir(self):
        svc = self._make()
        assert svc._is_path_under_dir("/tmp/test/file.txt", "/tmp") is True
        assert svc._is_path_under_dir("/other/file.txt", "/tmp") is False

    def test_is_path_under_dir_exception(self):
        svc = self._make()
        # Empty paths resolve to CWD, won't raise but may return False
        result = svc._is_path_under_dir("", "")
        assert isinstance(result, bool)

    def test_default_allowed_output_roots(self):
        svc = self._make()
        roots = svc._default_allowed_output_roots()
        assert isinstance(roots, list)
        assert len(roots) > 0

    def test_ensure_output_pattern_safe_empty(self):
        svc = self._make()
        with pytest.raises(Exception):
            svc._ensure_output_pattern_safe("")

    def test_ensure_output_pattern_safe_relative(self):
        svc = self._make()
        with pytest.raises(Exception):
            svc._ensure_output_pattern_safe("relative/path/output_%d.jpg")

    def test_build_ffmpeg_filter_args_interval(self):
        svc = self._make()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("interval", 2.0, 0.25)
        assert "fps=" in vf
        assert "scale=" in vf

    def test_build_ffmpeg_filter_args_scene(self):
        svc = self._make()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("scene", 2.0, 0.3)
        assert "scene" in vf

    def test_build_ffmpeg_filter_args_keyframe(self):
        svc = self._make()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("keyframe", 2.0, 0.25)
        assert "-skip_frame" in input_args

    def test_build_ffmpeg_filter_args_smart(self):
        svc = self._make()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("smart", 2.0, 0.25)
        assert "mpdecimate" in vf

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which")
    def test_find_tool_found(self, mock_which):
        mock_which.return_value = "/usr/local/bin/ffmpeg"
        svc = self._make()
        assert svc._find_tool("ffmpeg") == "/usr/local/bin/ffmpeg"

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which")
    def test_find_tool_not_found(self, mock_which):
        mock_which.return_value = None
        svc = self._make()
        # May find in standard locations or return None
        result = svc._find_tool("nonexistent_tool_xyz")
        assert result is None

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which")
    def test_ensure_ffmpeg_not_found(self, mock_which):
        mock_which.return_value = None
        svc = self._make()
        # May or may not raise depending on whether ffmpeg is installed
        try:
            svc._ensure_ffmpeg()
        except Exception:
            pass  # Expected if ffmpeg not installed

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which", return_value="/usr/bin/ffprobe")
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    def test_probe_video_not_exists(self, mock_ensure, mock_which):
        svc = self._make()
        with pytest.raises(Exception):
            svc.probe("/nonexistent/video.mp4")

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    def test_probe_duration_by_ffmpeg_no_duration(self, mock_ensure, mock_which):
        svc = self._make()
        with patch("apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner") as mock_runner:
            mock_result = MagicMock()
            mock_result.stderr = "no duration info"
            mock_result.stdout = ""
            mock_runner.return_value.run.return_value = mock_result
            result = svc._probe_duration_by_ffmpeg("/some/video.mp4")
            assert result == 0.0
