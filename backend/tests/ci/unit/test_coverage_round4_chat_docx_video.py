"""Coverage round 4: docx_export_service + video_frame_extract_service."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch, mock_open

import pytest

from apps.core.exceptions import ValidationException


# ============================================================
# docx_export_service.py
# ============================================================

class TestDocxExportService:
    def _make_service(self):
        from apps.chat_records.services.export.docx_export_service import DocxExportService
        return DocxExportService()

    def test_build_docx_bytes_empty_screenshots(self):
        svc = self._make_service()
        project = MagicMock()
        from apps.chat_records.services.export.export_types import ExportLayout
        layout = ExportLayout(images_per_page=1, show_page_number=False, header_text="")
        with pytest.raises(ValidationException, match="没有截图"):
            svc._build_docx_bytes(project=project, screenshots=[], layout=layout)

    def test_build_docx_bytes_single_image(self):
        svc = self._make_service()
        project = MagicMock()
        shot = MagicMock()
        shot.title = "Title"
        shot.note = "Note"
        from apps.chat_records.services.export.export_types import ExportLayout
        layout = ExportLayout(images_per_page=1, show_page_number=False, header_text="")
        with patch("docx.Document") as MockDoc:
            mock_doc = MagicMock()
            mock_section = MagicMock()
            mock_doc.sections = [mock_section]
            MockDoc.return_value = mock_doc
            with patch.object(svc, '_insert_docx_image'):
                with patch.object(svc, '_setup_docx_sections'):
                    result = svc._build_docx_bytes(project=project, screenshots=[shot], layout=layout)
        assert isinstance(result, bytes)

    def test_build_docx_bytes_two_per_page(self):
        svc = self._make_service()
        project = MagicMock()
        shots = [MagicMock(title="A", note=""), MagicMock(title="B", note="")]
        from apps.chat_records.services.export.export_types import ExportLayout
        layout = ExportLayout(images_per_page=2, show_page_number=False, header_text="")
        with patch("docx.Document") as MockDoc:
            mock_doc = MagicMock()
            mock_section = MagicMock()
            mock_doc.sections = [mock_section]
            MockDoc.return_value = mock_doc
            with patch.object(svc, '_insert_docx_image'):
                with patch.object(svc, '_setup_docx_sections'):
                    result = svc._build_docx_bytes(project=project, screenshots=shots, layout=layout)
        assert isinstance(result, bytes)

    def test_export_docx_returns_content_file(self):
        svc = self._make_service()
        project = MagicMock()
        shots = [MagicMock(title="T", note="")]
        from apps.chat_records.services.export.export_types import ExportLayout
        layout = ExportLayout(images_per_page=1, show_page_number=False, header_text="")
        with patch.object(svc, '_build_docx_bytes', return_value=b"docx_bytes"):
            result = svc.export_docx(project=project, screenshots=shots, layout=layout, filename="test.docx")
        assert result.name == "test.docx"

    def test_insert_docx_image_failure_raises(self):
        svc = self._make_service()
        cell = MagicMock()
        shot = MagicMock()
        shot.image.open.side_effect = RuntimeError("cannot open")
        with pytest.raises(ValidationException, match="插图失败"):
            svc._insert_docx_image(cell, shot, MagicMock())

    def test_setup_docx_sections_with_page_number(self):
        svc = self._make_service()
        from apps.chat_records.services.export.export_types import ExportLayout
        layout = ExportLayout(images_per_page=1, show_page_number=True, header_text="Header Text")
        mock_doc = MagicMock()
        mock_section = MagicMock()
        mock_footer = MagicMock()
        mock_para = MagicMock()
        mock_footer.paragraphs = [mock_para]
        mock_section.footer = mock_footer
        mock_doc.sections = [mock_section]
        mock_doc.styles = {"Title": MagicMock()}
        svc._setup_docx_sections(mock_doc, layout)
        mock_para.add_run.assert_any_call("第 ")
        mock_para.add_run.assert_any_call(" / ")
        mock_para.add_run.assert_any_call(" 页")


# ============================================================
# video_frame_extract_service.py
# ============================================================

class TestVideoFrameExtractService:
    def _make_service(self):
        from apps.chat_records.services.extraction.video_frame_extract_service import VideoFrameExtractService
        return VideoFrameExtractService()

    def test_estimate_total_frames(self):
        svc = self._make_service()
        assert svc.estimate_total_frames(10.0, 1.0) == 10
        assert svc.estimate_total_frames(10.5, 1.0) == 11
        assert svc.estimate_total_frames(0, 1.0) == 0
        assert svc.estimate_total_frames(10.0, 0) == 0

    def test_build_ffmpeg_filter_args_interval(self):
        svc = self._make_service()
        input_args, vf, extra_args = svc._build_ffmpeg_filter_args("interval", 2.0, 0.25)
        assert "fps=0.5" in vf
        assert extra_args == []

    def test_build_ffmpeg_filter_args_scene(self):
        svc = self._make_service()
        input_args, vf, extra_args = svc._build_ffmpeg_filter_args("scene", 1.0, 0.3)
        assert "scene" in vf
        assert "-vsync" in extra_args

    def test_build_ffmpeg_filter_args_keyframe(self):
        svc = self._make_service()
        input_args, vf, extra_args = svc._build_ffmpeg_filter_args("keyframe", 1.0, 0.25)
        assert "-skip_frame" in input_args
        assert "mpdecimate" in vf

    def test_build_ffmpeg_filter_args_smart(self):
        svc = self._make_service()
        input_args, vf, extra_args = svc._build_ffmpeg_filter_args("smart", 1.0, 0.25)
        assert "mpdecimate" in vf
        assert "-vsync" in extra_args

    def test_probe_video_not_exists(self):
        svc = self._make_service()
        with patch.object(svc, '_ensure_ffmpeg'):
            with pytest.raises(ValidationException, match="不存在"):
                svc.probe("/nonexistent/video.mp4")

    def test_probe_empty_path(self):
        svc = self._make_service()
        with patch.object(svc, '_ensure_ffmpeg'):
            with pytest.raises(ValidationException, match="不存在"):
                svc.probe("")

    def test_ensure_ffmpeg_raises_when_not_found(self):
        svc = self._make_service()
        with patch.object(svc, '_find_tool', return_value=None):
            with pytest.raises(ValidationException, match="ffmpeg"):
                svc._ensure_ffmpeg()

    def test_ensure_ffmpeg_does_not_raise_when_found(self):
        svc = self._make_service()
        with patch.object(svc, '_find_tool', return_value="/usr/bin/ffmpeg"):
            svc._ensure_ffmpeg()

    def test_check_ffmpeg_exit_zero(self):
        svc = self._make_service()
        proc = MagicMock()
        proc.wait.return_value = 0
        svc._check_ffmpeg_exit(proc)

    def test_check_ffmpeg_exit_nonzero_with_stderr(self):
        svc = self._make_service()
        proc = MagicMock()
        proc.wait.return_value = 1
        proc.stderr.read.return_value = "error: codec not found\nline2\nline3"
        with pytest.raises(ValidationException, match="ffmpeg 抽帧失败"):
            svc._check_ffmpeg_exit(proc)

    def test_check_ffmpeg_exit_nonzero_no_stderr(self):
        svc = self._make_service()
        proc = MagicMock()
        proc.wait.return_value = 1
        proc.stderr = None
        with pytest.raises(ValidationException, match="ffmpeg 抽帧失败"):
            svc._check_ffmpeg_exit(proc)

    def test_force_kill_proc(self):
        svc = self._make_service()
        proc = MagicMock()
        proc.wait.return_value = None
        svc._force_kill_proc(proc)
        proc.terminate.assert_called_once()

    def test_ensure_output_pattern_safe_empty(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="输出路径不能为空"):
            svc._ensure_output_pattern_safe("")

    def test_ensure_output_pattern_safe_relative(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="绝对路径"):
            svc._ensure_output_pattern_safe("relative/path/frame.jpg")

    def test_probe_duration_by_ffmpeg(self):
        svc = self._make_service()
        mock_result = MagicMock()
        mock_result.stderr = "Duration: 00:01:30.50"
        mock_result.stdout = ""
        with patch("apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner") as MockRunner:
            MockRunner.return_value.run.return_value = mock_result
            result = svc._probe_duration_by_ffmpeg("/tmp/video.mp4")
        assert result == 90.5

    def test_probe_duration_by_ffmpeg_no_match(self):
        svc = self._make_service()
        mock_result = MagicMock()
        mock_result.stderr = ""
        mock_result.stdout = ""
        with patch("apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner") as MockRunner:
            MockRunner.return_value.run.return_value = mock_result
            result = svc._probe_duration_by_ffmpeg("/tmp/video.mp4")
        assert result == 0.0

    def test_probe_duration_by_ffmpeg_exception(self):
        svc = self._make_service()
        with patch("apps.chat_records.services.extraction.video_frame_extract_service.SubprocessRunner") as MockRunner:
            MockRunner.return_value.run.side_effect = RuntimeError("fail")
            result = svc._probe_duration_by_ffmpeg("/tmp/video.mp4")
        assert result == 0.0
