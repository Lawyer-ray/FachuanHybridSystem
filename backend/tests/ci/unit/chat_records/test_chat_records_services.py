"""
Tests for apps.chat_records.services — 聊天记录服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import PermissionDenied


class TestAccessPolicy:
    """访问策略测试"""

    def test_admin_can_access(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        admin = MagicMock()
        admin.is_staff = True
        # Should not raise
        ensure_can_access_project(user=admin, project=MagicMock())

    def test_no_user_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=None, project=MagicMock())

    def test_anonymous_user_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = False
        user.is_admin = False
        user.is_superuser = False
        user.is_staff = False
        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=user, project=MagicMock())

    def test_owner_can_access(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_admin = False
        user.is_superuser = False
        user.id = 42
        project = MagicMock()
        project.created_by_id = 42
        # Should not raise
        ensure_can_access_project(user=user, project=project)

    def test_non_owner_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_admin = False
        user.is_superuser = False
        user.id = 42
        project = MagicMock()
        project.created_by_id = 99
        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=user, project=project)


class TestChatRecordsModules:
    """聊天记录模块可导入性测试"""

    def test_protocols_importable(self) -> None:
        from apps.chat_records.services.core import protocols

        assert protocols is not None

    def test_export_task_service_importable(self) -> None:
        from apps.chat_records.services.export import export_task_service

        assert export_task_service is not None

# ---------------------------------------------------------------------------
# VideoFrameExtractService extended tests
# ---------------------------------------------------------------------------

class TestVideoFrameExtractServiceExtended:
    def _make_service(self):
        from apps.chat_records.services.extraction.video_frame_extract_service import VideoFrameExtractService
        return VideoFrameExtractService()

    def test_is_path_under_dir_true(self):
        svc = self._make_service()
        assert svc._is_path_under_dir("/tmp/sub/file.txt", "/tmp") is True

    def test_is_path_under_dir_false(self):
        svc = self._make_service()
        assert svc._is_path_under_dir("/etc/passwd", "/tmp") is False

    def test_estimate_total_frames_basic(self):
        svc = self._make_service()
        assert svc.estimate_total_frames(10.0, 1.0) == 10

    def test_estimate_total_frames_zero_duration(self):
        svc = self._make_service()
        assert svc.estimate_total_frames(0, 1.0) == 0

    def test_estimate_total_frames_zero_interval(self):
        svc = self._make_service()
        assert svc.estimate_total_frames(10.0, 0) == 0

    def test_estimate_total_frames_rounds_up(self):
        svc = self._make_service()
        assert svc.estimate_total_frames(10.0, 3.0) == 4  # ceil(10/3) = 4

    def test_build_ffmpeg_filter_args_interval(self):
        svc = self._make_service()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("interval", 1.0, 0.25)
        assert "fps=" in vf

    def test_build_ffmpeg_filter_args_scene(self):
        svc = self._make_service()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("scene", 1.0, 0.25)
        assert "scene" in vf

    def test_build_ffmpeg_filter_args_keyframe(self):
        svc = self._make_service()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("keyframe", 1.0, 0.25)
        assert "-skip_frame" in input_args

    def test_build_ffmpeg_filter_args_smart(self):
        svc = self._make_service()
        input_args, vf, extra = svc._build_ffmpeg_filter_args("smart", 1.0, 0.25)
        assert "mpdecimate" in vf

    def test_ensure_output_pattern_safe_empty_raises(self):
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._ensure_output_pattern_safe("")

    def test_ensure_output_pattern_safe_relative_raises(self):
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._ensure_output_pattern_safe("relative/path/output.jpg")
