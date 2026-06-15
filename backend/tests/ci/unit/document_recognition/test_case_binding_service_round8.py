"""case_binding_service.py — round8 tests for remaining uncovered branches.

Covers 44 missing: create_case_log, _update_log_reminder, bind_document_to_case,
manual_bind_document_to_case, _trigger_notification, format_log_content.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.document_recognition.services.case_binding_service import CaseBindingService
from apps.document_recognition.services.data_classes import BindingResult, DocumentType


def _make_service(case_service=None):
    return CaseBindingService(case_service=case_service or MagicMock())


# ── create_case_log ────────────────────────────────────────────────────


class TestCreateCaseLog:
    @pytest.mark.django_db
    def test_basic_flow_no_reminder(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=None, file_path=""
        )
        assert result == 10
        svc.case_service.create_case_log_internal.assert_called_once()

    @pytest.mark.django_db
    def test_with_file_path(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.add_case_log_attachment_internal.return_value = True

        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=None, file_path="/tmp/test.pdf"
        )
        assert result == 10
        svc.case_service.add_case_log_attachment_internal.assert_called_once()

    @pytest.mark.django_db
    def test_with_file_addition_fails(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.add_case_log_attachment_internal.return_value = False

        # Should not raise, just log warning
        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=None, file_path="/tmp/test.pdf"
        )
        assert result == 10

    @pytest.mark.django_db
    def test_with_reminder_time(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.update_case_log_reminder_internal.return_value = True

        dt = datetime(2024, 6, 15, 9, 0)
        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=dt, file_path=""
        )
        assert result == 10
        svc.case_service.update_case_log_reminder_internal.assert_called_once()

    @pytest.mark.django_db
    def test_with_reminder_update_fails(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.update_case_log_reminder_internal.return_value = False

        dt = datetime(2024, 6, 15, 9, 0)
        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=dt, file_path=""
        )
        assert result == 10

    @pytest.mark.django_db
    def test_with_reminder_exception(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.update_case_log_reminder_internal.side_effect = RuntimeError("db error")

        dt = datetime(2024, 6, 15, 9, 0)
        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=dt, file_path=""
        )
        assert result == 10

    @pytest.mark.django_db
    def test_with_user(self):
        svc = _make_service()
        svc.case_service.create_case_log_internal.return_value = 10
        user = MagicMock()
        user.id = 5

        result = svc.create_case_log(
            case_id=1, content="test", reminder_time=None, file_path="", user=user
        )
        assert result == 10
        call_kwargs = svc.case_service.create_case_log_internal.call_args[1]
        assert call_kwargs["user_id"] == 5


# ── _update_log_reminder ───────────────────────────────────────────────


class TestUpdateLogReminder:
    def test_summons_type(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.return_value = True

        dt = datetime(2024, 6, 15, 9, 0)
        svc._update_log_reminder(10, dt, DocumentType.SUMMONS)

        call_kwargs = svc.case_service.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "hearing"

    def test_execution_ruling_type(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.return_value = True

        dt = datetime(2024, 6, 15, 9, 0)
        svc._update_log_reminder(10, dt, DocumentType.EXECUTION_RULING)

        call_kwargs = svc.case_service.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "asset_preservation_expires"

    def test_other_type(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.return_value = True

        dt = datetime(2024, 6, 15, 9, 0)
        svc._update_log_reminder(10, dt, DocumentType.OTHER)

        call_kwargs = svc.case_service.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "other"

    def test_none_document_type(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.return_value = True

        dt = datetime(2024, 6, 15, 9, 0)
        svc._update_log_reminder(10, dt, None)

        call_kwargs = svc.case_service.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "other"

    def test_update_returns_false(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.return_value = False

        dt = datetime(2024, 6, 15, 9, 0)
        # Should not raise
        svc._update_log_reminder(10, dt, DocumentType.SUMMONS)

    def test_update_raises_exception(self):
        svc = _make_service()
        svc.case_service.update_case_log_reminder_internal.side_effect = Exception("db error")

        dt = datetime(2024, 6, 15, 9, 0)
        # Should not raise, just log
        svc._update_log_reminder(10, dt, DocumentType.SUMMONS)


# ── bind_document_to_case ──────────────────────────────────────────────


@pytest.mark.django_db
class TestBindDocumentToCase:
    def test_empty_case_number(self):
        svc = _make_service()
        result = svc.bind_document_to_case(
            case_number="",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=None,
            file_path="/tmp/test.pdf",
        )
        assert not result.success
        assert result.error_code == "CASE_NUMBER_NOT_FOUND"

    def test_case_not_found(self):
        svc = _make_service()
        svc.case_service.search_cases_by_case_number_internal.return_value = []

        result = svc.bind_document_to_case(
            case_number="（2024）京01民初123号",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=None,
            file_path="/tmp/test.pdf",
        )
        assert not result.success
        assert result.error_code == "CASE_NOT_FOUND"

    def test_case_dto_not_found(self):
        svc = _make_service()
        mock_case = MagicMock()
        mock_case.id = 1
        svc.case_service.search_cases_by_case_number_internal.return_value = [mock_case]
        svc.case_service.get_case_by_id_internal.return_value = None

        result = svc.bind_document_to_case(
            case_number="（2024）京01民初123号",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=None,
            file_path="/tmp/test.pdf",
        )
        assert not result.success

    def test_successful_binding(self):
        svc = _make_service()
        mock_case = MagicMock()
        mock_case.id = 1
        svc.case_service.search_cases_by_case_number_internal.return_value = [mock_case]

        case_dto = MagicMock()
        case_dto.name = "张三诉李四"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.return_value = 42

        result = svc.bind_document_to_case(
            case_number="（2024）京01民初123号",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=datetime(2024, 6, 15),
            file_path="/tmp/test.pdf",
        )
        assert result.success
        assert result.case_id == 1
        assert result.case_name == "张三诉李四"
        assert result.case_log_id == 42

    def test_create_log_raises_not_found(self):
        from apps.core.exceptions import NotFoundError

        svc = _make_service()
        mock_case = MagicMock()
        mock_case.id = 1
        svc.case_service.search_cases_by_case_number_internal.return_value = [mock_case]

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.side_effect = NotFoundError("not found")

        result = svc.bind_document_to_case(
            case_number="（2024）京01民初123号",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=None,
            file_path="/tmp/test.pdf",
        )
        assert not result.success
        assert result.error_code == "CASE_NOT_FOUND"

    def test_create_log_raises_general_exception(self):
        svc = _make_service()
        mock_case = MagicMock()
        mock_case.id = 1
        svc.case_service.search_cases_by_case_number_internal.return_value = [mock_case]

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.side_effect = RuntimeError("db error")

        result = svc.bind_document_to_case(
            case_number="（2024）京01民初123号",
            document_type=DocumentType.SUMMONS,
            content="test",
            key_time=None,
            file_path="/tmp/test.pdf",
        )
        assert not result.success
        assert result.error_code == "BINDING_ERROR"


# ── format_log_content ─────────────────────────────────────────────────


class TestFormatLogContent:
    def test_summons_full(self):
        svc = _make_service()
        result = svc.format_log_content(
            document_type=DocumentType.SUMMONS,
            case_number="（2024）京01民初123号",
            key_time=datetime(2024, 6, 15, 9, 30),
            raw_text="some text content here",
        )
        assert "【传票】" in result
        assert "案号：（2024）京01民初123号" in result
        assert "开庭时间：2024-06-15 09:30" in result
        assert "some text content here" in result

    def test_execution_ruling(self):
        svc = _make_service()
        result = svc.format_log_content(
            document_type=DocumentType.EXECUTION_RULING,
            case_number=None,
            key_time=datetime(2024, 6, 15),
            raw_text="",
        )
        assert "【执行裁定书】" in result
        assert "保全到期时间：2024-06-15" in result
        assert "案号" not in result

    def test_other_type(self):
        svc = _make_service()
        result = svc.format_log_content(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="text",
        )
        assert "【其他文书】" in result

    def test_long_text_truncated(self):
        svc = _make_service()
        long_text = "x" * 600
        result = svc.format_log_content(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text=long_text,
        )
        assert "..." in result
        assert len(result) < 700

    def test_no_case_number_no_time(self):
        svc = _make_service()
        result = svc.format_log_content(
            document_type=DocumentType.SUMMONS,
            case_number=None,
            key_time=None,
            raw_text="",
        )
        assert "案号" not in result
        assert "开庭时间" not in result


# ── _trigger_notification ──────────────────────────────────────────────


class TestTriggerNotification:
    @patch("apps.document_recognition.services.notification_service.DocumentRecognitionNotificationService")
    def test_notification_success(self, MockNotif):
        svc = _make_service()
        task = MagicMock()
        task.id = 1
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        task.case_number = "123"
        task.key_time = datetime(2024, 6, 15)

        notif_result = MagicMock()
        notif_result.success = True
        notif_result.sent_at = datetime(2024, 6, 15)
        notif_result.file_sent = True
        MockNotif.return_value.send_notification.return_value = notif_result

        svc._trigger_notification(task, 1, "Test Case", DocumentType.SUMMONS)
        assert task.notification_sent is True
        assert task.notification_file_sent is True
        task.save.assert_called_once()

    @patch("apps.document_recognition.services.notification_service.DocumentRecognitionNotificationService")
    def test_notification_failure(self, MockNotif):
        svc = _make_service()
        task = MagicMock()
        task.id = 1
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        task.case_number = "123"
        task.key_time = datetime(2024, 6, 15)

        notif_result = MagicMock()
        notif_result.success = False
        notif_result.message = "send failed"
        notif_result.file_sent = False
        MockNotif.return_value.send_notification.return_value = notif_result

        svc._trigger_notification(task, 1, "Test", DocumentType.SUMMONS)
        assert task.notification_sent is False
        assert task.notification_error == "send failed"
        task.save.assert_called_once()

    @patch("apps.document_recognition.services.notification_service.DocumentRecognitionNotificationService")
    def test_notification_exception(self, MockNotif):
        svc = _make_service()
        task = MagicMock()
        task.id = 1
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"

        MockNotif.side_effect = RuntimeError("import error")

        svc._trigger_notification(task, 1, "Test", DocumentType.SUMMONS)
        assert task.notification_sent is False
        task.save.assert_called()

    @patch("apps.document_recognition.services.notification_service.DocumentRecognitionNotificationService")
    def test_notification_uses_renamed_path(self, MockNotif):
        svc = _make_service()
        task = MagicMock()
        task.id = 1
        task.renamed_file_path = "/tmp/renamed.pdf"
        task.file_path = "/tmp/old.pdf"
        task.case_number = "123"
        task.key_time = None

        notif_result = MagicMock()
        notif_result.success = True
        notif_result.sent_at = datetime(2024, 6, 15)
        notif_result.file_sent = False
        MockNotif.return_value.send_notification.return_value = notif_result

        svc._trigger_notification(task, 1, "Test", DocumentType.OTHER)
        call_kwargs = MockNotif.return_value.send_notification.call_args[1]
        assert call_kwargs["file_path"] == "/tmp/renamed.pdf"


# ── manual_bind_document_to_case ───────────────────────────────────────


@pytest.mark.django_db
class TestManualBindDocumentToCase:
    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_task_not_found(self, MockTask):
        svc = _make_service()
        MockTask.DoesNotExist = Exception
        MockTask.objects.get.side_effect = MockTask.DoesNotExist

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert not result.success
        assert result.error_code == "TASK_NOT_FOUND"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_task_already_bound(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = True
        MockTask.objects.get.return_value = task

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert not result.success
        assert result.error_code == "ALREADY_BOUND"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_case_not_found(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = None
        MockTask.objects.get.return_value = task
        svc.case_service.get_case_by_id_internal.return_value = None

        result = svc.manual_bind_document_to_case(task_id=1, case_id=99)
        assert not result.success
        assert result.error_code == "CASE_NOT_FOUND"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_successful_manual_bind(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = "summons"
        task.case_number = "123"
        task.key_time = datetime(2024, 6, 15)
        task.raw_text = "some text"
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        MockTask.objects.get.return_value = task

        case_dto = MagicMock()
        case_dto.name = "Test Case"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.get_case_model_internal.return_value = MagicMock()
        svc.case_service.get_case_log_model_internal.return_value = MagicMock()

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert result.success
        assert result.case_id == 1

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_manual_bind_create_log_fails(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = None
        task.case_number = "123"
        task.key_time = None
        task.raw_text = ""
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        MockTask.objects.get.return_value = task

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.side_effect = Exception("db error")

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert not result.success
        assert result.error_code == "LOG_CREATE_ERROR"

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_manual_bind_save_task_fails(self, MockTask):
        from apps.core.exceptions import NotFoundError

        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = None
        task.case_number = "123"
        task.key_time = None
        task.raw_text = ""
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        task.save.side_effect = Exception("save error")
        MockTask.objects.get.return_value = task

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.get_case_model_internal.return_value = MagicMock()
        svc.case_service.get_case_log_model_internal.return_value = MagicMock()

        with pytest.raises(Exception, match="save error"):
            svc.manual_bind_document_to_case(task_id=1, case_id=1)

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_manual_bind_with_renamed_path(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = "execution"
        task.case_number = "456"
        task.key_time = datetime(2024, 6, 15)
        task.raw_text = "text"
        task.renamed_file_path = "/tmp/renamed.pdf"
        task.file_path = "/tmp/original.pdf"
        MockTask.objects.get.return_value = task

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.get_case_model_internal.return_value = MagicMock()
        svc.case_service.get_case_log_model_internal.return_value = MagicMock()

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert result.success

    @patch("apps.document_recognition.models.DocumentRecognitionTask")
    def test_manual_bind_invalid_document_type(self, MockTask):
        svc = _make_service()
        task = MagicMock()
        task.binding_success = False
        task.document_type = "invalid_type"
        task.case_number = "789"
        task.key_time = None
        task.raw_text = ""
        task.renamed_file_path = None
        task.file_path = "/tmp/test.pdf"
        MockTask.objects.get.return_value = task

        case_dto = MagicMock()
        case_dto.name = "Test"
        svc.case_service.get_case_by_id_internal.return_value = case_dto
        svc.case_service.create_case_log_internal.return_value = 10
        svc.case_service.get_case_model_internal.return_value = MagicMock()
        svc.case_service.get_case_log_model_internal.return_value = MagicMock()

        result = svc.manual_bind_document_to_case(task_id=1, case_id=1)
        assert result.success  # should use DocumentType.OTHER
