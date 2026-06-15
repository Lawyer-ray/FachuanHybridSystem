"""Tests for video_frame_extract_service.py — additional coverage.

Covers: _ensure_output_pattern_safe (unsafe dir), _probe_duration_by_ffmpeg,
        probe (with ffprobe), _find_tool (with standard paths),
        _check_ffmpeg_exit, _force_kill_proc, _build_ffmpeg_filter_args.
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import ValidationException
from apps.chat_records.services.extraction.video_frame_extract_service import (
    FFProbeInfo,
    VideoFrameExtractService,
)


@pytest.fixture
def svc() -> VideoFrameExtractService:
    return VideoFrameExtractService()


# ── _ensure_output_pattern_safe ──────────────────────────────────


class TestEnsureOutputPatternSafe:
    def test_empty_raises(self, svc: VideoFrameExtractService) -> None:
        with pytest.raises(ValidationException, match="输出路径不能为空"):
            svc._ensure_output_pattern_safe("")

    def test_relative_path_raises(self, svc: VideoFrameExtractService) -> None:
        with pytest.raises(ValidationException, match="绝对路径"):
            svc._ensure_output_pattern_safe("relative/path/output_%d.jpg")

    def test_unsafe_dir_raises(self, svc: VideoFrameExtractService) -> None:
        with pytest.raises(ValidationException, match="输出目录不安全"):
            svc._ensure_output_pattern_safe("/etc/output_%d.jpg")


# ── _probe_duration_by_ffmpeg ────────────────────────────────────


class TestProbeDurationByFfmpeg:
    def test_parses_duration(self, svc: VideoFrameExtractService) -> None:
        with patch(
            "apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner"
        ) as MockRunner:
            mock_result = MagicMock()
            mock_result.stderr = "Duration: 01:30:45.50"
            mock_result.stdout = ""
            MockRunner.return_value.run.return_value = mock_result
            result = svc._probe_duration_by_ffmpeg("/some/video.mp4")
            assert result == 1 * 3600 + 30 * 60 + 45.5

    def test_no_duration_match(self, svc: VideoFrameExtractService) -> None:
        with patch(
            "apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner"
        ) as MockRunner:
            mock_result = MagicMock()
            mock_result.stderr = "no duration here"
            mock_result.stdout = ""
            MockRunner.return_value.run.return_value = mock_result
            result = svc._probe_duration_by_ffmpeg("/some/video.mp4")
            assert result == 0.0

    def test_exception_returns_zero(self, svc: VideoFrameExtractService) -> None:
        with patch(
            "apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner"
        ) as MockRunner:
            MockRunner.return_value.run.side_effect = RuntimeError("cannot run")
            result = svc._probe_duration_by_ffmpeg("/some/video.mp4")
            assert result == 0.0


# ── probe ────────────────────────────────────────────────────────


class TestProbe:
    @patch.object(VideoFrameExtractService, "_find_tool", return_value="/usr/bin/ffprobe")
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    def test_valid_video_with_timebase(
        self, mock_ensure: MagicMock, mock_find: MagicMock, svc: VideoFrameExtractService
    ) -> None:
        import os
        # Create a temp file to pass the exists() check
        tmpfile = "/tmp/test_video_for_probe.mp4"
        with open(tmpfile, "w") as f:
            f.write("fake")

        try:
            with patch(
                "apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner"
            ) as MockRunner:
                mock_result = MagicMock()
                mock_result.stdout = '{"format": {"duration": "120.5"}, "streams": [{"time_base": "1/30000"}]}'
                mock_runner_instance = MagicMock()
                mock_runner_instance.run.return_value = mock_result
                MockRunner.return_value = mock_runner_instance
                result = svc.probe(tmpfile)
                assert result.duration_seconds == 120.5
                assert result.time_base_seconds == 1 / 30000
        finally:
            os.unlink(tmpfile)

    @patch.object(VideoFrameExtractService, "_find_tool", return_value=None)
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    @patch.object(VideoFrameExtractService, "_probe_duration_by_ffmpeg", return_value=0.0)
    def test_zero_duration_raises(
        self, mock_dur: MagicMock, mock_ensure: MagicMock, mock_find: MagicMock, svc: VideoFrameExtractService
    ) -> None:
        import os
        tmpfile = "/tmp/test_video_zero_dur.mp4"
        with open(tmpfile, "w") as f:
            f.write("fake")
        try:
            with pytest.raises(ValidationException, match="无法解析视频时长"):
                svc.probe(tmpfile)
        finally:
            os.unlink(tmpfile)

    @patch.object(VideoFrameExtractService, "_find_tool", return_value=None)
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    @patch.object(VideoFrameExtractService, "_probe_duration_by_ffmpeg", return_value=60.0)
    def test_fallback_to_ffmpeg_duration(
        self, mock_dur: MagicMock, mock_ensure: MagicMock, mock_find: MagicMock, svc: VideoFrameExtractService
    ) -> None:
        import os
        tmpfile = "/tmp/test_video_fallback.mp4"
        with open(tmpfile, "w") as f:
            f.write("fake")
        try:
            result = svc.probe(tmpfile)
            assert result.duration_seconds == 60.0
            assert result.time_base_seconds is None
        finally:
            os.unlink(tmpfile)

    @patch.object(VideoFrameExtractService, "_find_tool", return_value="/usr/bin/ffprobe")
    @patch.object(VideoFrameExtractService, "_ensure_ffmpeg")
    def test_ffprobe_parse_error(
        self, mock_ensure: MagicMock, mock_find: MagicMock, svc: VideoFrameExtractService
    ) -> None:
        """When ffprobe fails to parse, the exception is caught and duration=0,
        which triggers the 'cannot parse duration' ValidationException."""
        import os
        tmpfile = "/tmp/test_video_err.mp4"
        with open(tmpfile, "w") as f:
            f.write("fake")
        try:
            with patch(
                "apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner"
            ) as MockRunner:
                mock_runner = MagicMock()
                mock_runner.run.side_effect = RuntimeError("parse error")
                MockRunner.return_value = mock_runner
                # ffprobe fails → duration=0 → raises
                with pytest.raises(ValidationException, match="无法解析视频时长"):
                    svc.probe(tmpfile)
        finally:
            os.unlink(tmpfile)


# ── _find_tool ───────────────────────────────────────────────────


class TestFindTool:
    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which")
    def test_found_via_shutil(self, mock_which: MagicMock, svc: VideoFrameExtractService) -> None:
        mock_which.return_value = "/usr/bin/ffmpeg"
        assert svc._find_tool("ffmpeg") == "/usr/bin/ffmpeg"

    @patch("apps.chat_records.services.extraction.video_frame_extract_service.shutil.which")
    def test_not_found_checks_standard_paths(
        self, mock_which: MagicMock, svc: VideoFrameExtractService
    ) -> None:
        mock_which.return_value = None
        with patch(
            "apps.chat_records.services.extraction.video_frame_extract_service.Path"
        ) as MockPath:
            # All paths don't exist
            MockPath.return_value.exists.return_value = False
            result = svc._find_tool("ffmpeg")
            assert result is None


# ── _check_ffmpeg_exit ───────────────────────────────────────────


class TestCheckFfmpegExit:
    def test_zero_exit(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.return_value = 0
        # Should not raise
        svc._check_ffmpeg_exit(proc)

    def test_nonzero_exit_with_stderr(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.return_value = 1
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = "Error: something failed\nLine 2"
        with pytest.raises(ValidationException, match="ffmpeg 抽帧失败"):
            svc._check_ffmpeg_exit(proc)

    def test_nonzero_exit_no_stderr(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.return_value = 1
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""
        with pytest.raises(ValidationException, match="ffmpeg 抽帧失败"):
            svc._check_ffmpeg_exit(proc)

    def test_wait_timeout_kills(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.side_effect = [TimeoutError, 0]
        proc.stderr = None
        svc._check_ffmpeg_exit(proc)
        proc.kill.assert_called_once()


# ── _force_kill_proc ─────────────────────────────────────────────


class TestForceKillProc:
    def test_terminates_and_waits(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.return_value = 0
        svc._force_kill_proc(proc)
        proc.terminate.assert_called_once()
        proc.wait.assert_called()

    def test_wait_timeout_kills(self, svc: VideoFrameExtractService) -> None:
        proc = MagicMock()
        proc.wait.side_effect = [TimeoutError, 0]
        svc._force_kill_proc(proc)
        proc.kill.assert_called_once()


# ── _build_ffmpeg_filter_args ────────────────────────────────────


class TestBuildFfmpegFilterArgs:
    def test_scene_strategy(self, svc: VideoFrameExtractService) -> None:
        input_args, vf, extra = svc._build_ffmpeg_filter_args("scene", 2.0, 0.3)
        assert "scene" in vf
        assert "0.3" in vf
        assert input_args == []

    def test_keyframe_strategy(self, svc: VideoFrameExtractService) -> None:
        input_args, vf, extra = svc._build_ffmpeg_filter_args("keyframe", 2.0, 0.25)
        assert "-skip_frame" in input_args
        assert "nokey" in input_args

    def test_smart_strategy(self, svc: VideoFrameExtractService) -> None:
        input_args, vf, extra = svc._build_ffmpeg_filter_args("smart", 2.0, 0.25)
        assert "mpdecimate" in vf
        assert extra == ["-vsync", "vfr", "-frame_pts", "1"]

    def test_interval_strategy(self, svc: VideoFrameExtractService) -> None:
        input_args, vf, extra = svc._build_ffmpeg_filter_args("interval", 2.0, 0.25)
        assert "fps=0.5" in vf

    def test_unknown_strategy_defaults_to_fps(self, svc: VideoFrameExtractService) -> None:
        input_args, vf, extra = svc._build_ffmpeg_filter_args("unknown", 0.5, 0.25)
        assert "fps=2.0" in vf
        assert input_args == []
        assert extra == []


# ── estimate_total_frames ────────────────────────────────────────


class TestEstimateTotalFrames:
    def test_normal(self, svc: VideoFrameExtractService) -> None:
        assert svc.estimate_total_frames(10.0, 2.0) == 5

    def test_zero_duration(self, svc: VideoFrameExtractService) -> None:
        assert svc.estimate_total_frames(0.0, 1.0) == 0

    def test_zero_interval(self, svc: VideoFrameExtractService) -> None:
        assert svc.estimate_total_frames(10.0, 0.0) == 0

    def test_fractional(self, svc: VideoFrameExtractService) -> None:
        assert svc.estimate_total_frames(10.0, 3.0) == 4  # ceil(10/3)
