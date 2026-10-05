"""RecordingService 单元测试。

覆盖 get_recording 的命中/404/无权访问、delete_recording 的
RUNNING 拒删与成功删除（含 video 存储文件清理）、update_duration、
_get_max_video_size_bytes 的默认值/有效配置/脏配置三分支。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.chat_records.models import ChatRecordProject, ChatRecordRecording, ExtractStatus
from apps.chat_records.services.core.project_service import ProjectService
from apps.chat_records.services.extraction.recording_service import RecordingService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.testing.factories import LawyerFactory


def _service() -> RecordingService:
    return RecordingService(project_service=ProjectService())


@pytest.fixture
def owner(db: None):
    return LawyerFactory()


@pytest.fixture
def admin_user(db: None):
    return LawyerFactory(is_admin=True)


@pytest.fixture
def project(db: None, owner) -> ChatRecordProject:
    return ChatRecordProject.objects.create(name="录屏服务项目", created_by=owner)


def _recording(project: ChatRecordProject, *, status: str = ExtractStatus.PENDING) -> ChatRecordRecording:
    video = SimpleUploadedFile("screen.mp4", b"fake-mp4-bytes", content_type="video/mp4")
    return ChatRecordRecording.objects.create(
        project=project,
        video=video,
        original_name="screen.mp4",
        size_bytes=15,
        extract_status=status,
    )


@pytest.mark.django_db
class TestGetRecording:
    def test_not_found_raises(self, owner) -> None:
        with pytest.raises(NotFoundError, match="录屏"):
            _service().get_recording(user=owner, recording_id="0192f0de-0000-7000-8000-000000000001")

    def test_owner_can_read(self, project, owner) -> None:
        recording = _recording(project)
        got = _service().get_recording(user=owner, recording_id=str(recording.id))
        assert got.pk == recording.pk

    def test_admin_can_read_others(self, project, admin_user) -> None:
        recording = _recording(project)
        got = _service().get_recording(user=admin_user, recording_id=str(recording.id))
        assert got.pk == recording.pk

    def test_other_user_denied(self, project) -> None:
        other = LawyerFactory()
        recording = _recording(project)
        with pytest.raises(PermissionDenied):
            _service().get_recording(user=other, recording_id=str(recording.id))


@pytest.mark.django_db
class TestDeleteRecording:
    def test_running_recording_rejected(self, project, owner) -> None:
        recording = _recording(project, status=ExtractStatus.RUNNING)
        with pytest.raises(ValidationException, match="抽帧处理中"):
            _service().delete_recording(user=owner, recording_id=str(recording.id))
        recording.refresh_from_db()
        assert recording.pk == recording.pk  # 仍存在

    def test_delete_removes_record_and_video_file(self, project, owner, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        recording = _recording(project)
        stored_path = Path(recording.video.path)
        assert stored_path.exists()

        result = _service().delete_recording(user=owner, recording_id=str(recording.id))

        assert result == {"success": True}
        assert not ChatRecordRecording.objects.filter(pk=recording.pk).exists()
        assert not stored_path.exists()


@pytest.mark.django_db
class TestUpdateDuration:
    def test_updates_duration_field(self, project, owner) -> None:
        recording = _recording(project)
        updated = _service().update_duration(user=owner, recording_id=str(recording.id), duration_seconds=123.5)
        updated.refresh_from_db()
        assert updated.duration_seconds == 123.5

    def test_duration_none_allowed(self, project, owner) -> None:
        recording = _recording(project)
        updated = _service().update_duration(user=owner, recording_id=str(recording.id), duration_seconds=None)
        updated.refresh_from_db()
        assert updated.duration_seconds is None


class TestGetMaxVideoSizeBytes:
    def _svc(self) -> RecordingService:
        return RecordingService(project_service=MagicMock())

    def test_default_when_config_empty(self) -> None:
        with patch(
            "apps.core.services.system_config_service.SystemConfigService.get_value",
            return_value="",
        ):
            assert self._svc()._get_max_video_size_bytes() == RecordingService.DEFAULT_MAX_VIDEO_SIZE_BYTES

    def test_config_value_parsed(self) -> None:
        with patch(
            "apps.core.services.system_config_service.SystemConfigService.get_value",
            return_value="1024",
        ):
            assert self._svc()._get_max_video_size_bytes() == 1024

    def test_invalid_config_falls_back_to_default(self) -> None:
        with patch(
            "apps.core.services.system_config_service.SystemConfigService.get_value",
            return_value="not-a-number",
        ):
            assert self._svc()._get_max_video_size_bytes() == RecordingService.DEFAULT_MAX_VIDEO_SIZE_BYTES
