from __future__ import annotations

import io
import os
import tempfile
from types import SimpleNamespace

import pytest

from apps.chat_records.services.video_frame_extract_service import VideoFrameExtractService
from apps.core.exceptions import ValidationException


def test_iter_ffmpeg_progress_rejects_unsafe_output_dir(monkeypatch):
    monkeypatch.setattr(VideoFrameExtractService, "_ensure_ffmpeg", lambda self: None)
    service = VideoFrameExtractService()
    it = service.iter_ffmpeg_progress(
        video_path="/tmp/video.mp4",
        output_pattern="/etc/frame_%06d.jpg",
        interval_seconds=1.0,
        timeout_seconds=1.0,
    )
    with pytest.raises(ValidationException):
        next(it)


def test_iter_ffmpeg_progress_times_out(monkeypatch):
    monkeypatch.setattr(VideoFrameExtractService, "_ensure_ffmpeg", lambda self: None)
    monkeypatch.setattr(VideoFrameExtractService, "_find_tool", lambda self, name: name)

    r, w = os.pipe()
    os.close(w)
    stdout = os.fdopen(r, "r", encoding="utf-8", closefd=True)

    class _FakeProc:
        def __init__(self):
            self.stdout = stdout
            self.stderr = io.StringIO("")

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            try:
                self.stdout.close()
            except Exception:
                pass

        def wait(self, timeout=None):
            raise TimeoutError()

    import apps.chat_records.services.video_frame_extract_service as mod

    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 100.0

    monkeypatch.setattr(mod.time, "monotonic", fake_monotonic)
    monkeypatch.setattr("apps.core.subprocess_runner.SubprocessRunner.popen", lambda *args, **kwargs: _FakeProc())

    service = VideoFrameExtractService()
    output_pattern = os.path.join(tempfile.gettempdir(), "frame_%06d.jpg")
    it = service.iter_ffmpeg_progress(
        video_path="/tmp/video.mp4",
        output_pattern=output_pattern,
        interval_seconds=1.0,
        timeout_seconds=0.01,
    )
    with pytest.raises(ValidationException):
        next(it)
