"""Coverage tests for document_recognition/services/case_binding_service.py."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.document_recognition.services.case_binding_service import CaseBindingService
from apps.document_recognition.services.data_classes import BindingResult, DocumentType, NotificationResult


class TestCaseBindingServiceInit:
    def test_default_init(self):
        svc = CaseBindingService()
        assert svc._case_service is None

    def test_injected_case_service(self):
        mock_service = MagicMock()
        svc = CaseBindingService(case_service=mock_service)
        assert svc._case_service is mock_service


class TestCaseServiceProperty:
    def test_lazy_load(self):
        svc = CaseBindingService()
        with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_cs = MagicMock()
            mock_locator.get_case_service.return_value = mock_cs
            result = svc.case_service
            assert result is mock_cs
            # Second call should use cached value
            result2 = svc.case_service
            assert result2 is mock_cs


class TestFindCaseByNumber:
    def test_empty_case_number(self):
        svc = CaseBindingService(case_service=MagicMock())
        assert svc.find_case_by_number("") is None
        assert svc.find_case_by_number("   ") is None
        assert svc.find_case_by_number(None) is None  # type: ignore[arg-type]

    def test_case_found(self):
        mock_cs = MagicMock()
        mock_case = MagicMock()
        mock_case.id = 42
        mock_cs.search_cases_by_case_number_internal.return_value = [mock_case]

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.find_case_by_number("（2024）京01民初123号")
        assert result == 42

    def test_case_not_found(self):
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = []

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.find_case_by_number("（2024）京01民初999号")
        assert result is None

    def test_exception_returns_none(self):
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.side_effect = Exception("db error")

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.find_case_by_number("（2024）京01民初123号")
        assert result is None


class TestCreateCaseLog:
    def test_create_writes_no_reminder(self):
        """原 test_create_with_reminder：绑定期不再写提醒（改造后行为）。"""
        mock_cs = MagicMock()
        mock_cs.create_case_log_internal.return_value = 100
        mock_cs.update_case_log_reminder_internal.return_value = True
        mock_cs.add_case_log_attachment_internal.return_value = True

        svc = CaseBindingService(case_service=mock_cs)
        # Call the underlying method directly to bypass @transaction.atomic
        result = svc.create_case_log.__wrapped__(
            svc,
            case_id=1,
            content="test content",
            file_path="/tmp/doc.pdf",
            user=MagicMock(id=1),
        )
        assert result == 100
        mock_cs.update_case_log_reminder_internal.assert_not_called()

    def test_create_without_reminder(self):
        mock_cs = MagicMock()
        mock_cs.create_case_log_internal.return_value = 101
        mock_cs.add_case_log_attachment_internal.return_value = True

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.create_case_log.__wrapped__(
            svc,
            case_id=1,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result == 101

    def test_create_with_empty_file_path(self):
        mock_cs = MagicMock()
        mock_cs.create_case_log_internal.return_value = 102

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.create_case_log.__wrapped__(
            svc,
            case_id=1,
            content="test",
            file_path="",
        )
        assert result == 102
        mock_cs.add_case_log_attachment_internal.assert_not_called()

    def test_attachment_failure_warns(self):
        mock_cs = MagicMock()
        mock_cs.create_case_log_internal.return_value = 103
        mock_cs.add_case_log_attachment_internal.return_value = False

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.create_case_log.__wrapped__(
            svc,
            case_id=1,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result == 103


class TestBindingWritesNoReminder:
    """原 TestUpdateLogReminder：_update_log_reminder 已删除，绑定期零提醒。"""

    def test_create_case_log_zero_update_calls(self):
        mock_cs = MagicMock()
        mock_cs.create_case_log_internal.return_value = 100
        mock_cs.update_case_log_reminder_internal.side_effect = Exception("update failed")

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.create_case_log.__wrapped__(svc, case_id=1, content="test", file_path="")
        assert result == 100
        mock_cs.update_case_log_reminder_internal.assert_not_called()

    def test_bind_document_zero_update_calls(self):
        mock_cs = MagicMock()
        mock_cs.get_case_by_id_internal.return_value = MagicMock(name="Test Case")
        mock_cs.update_case_log_reminder_internal.return_value = False

        svc = CaseBindingService(case_service=mock_cs)
        svc.create_case_log = MagicMock(return_value=200)
        result = svc.bind_document_to_case(
            case_id=42,
            document_type=DocumentType.SUMMONS,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is True
        mock_cs.update_case_log_reminder_internal.assert_not_called()


class TestBindDocumentToCase:
    def test_bind_directly_by_case_id(self):
        """原 test_empty_case_number：不再按案号搜索，直接给 case_id 即可绑定。"""
        mock_cs = MagicMock()
        mock_dto = MagicMock()
        mock_dto.name = "Test Case"
        mock_cs.get_case_by_id_internal.return_value = mock_dto

        svc = CaseBindingService(case_service=mock_cs)
        svc.create_case_log = MagicMock(return_value=200)
        result = svc.bind_document_to_case(
            case_id=42,
            document_type=DocumentType.SUMMONS,
            content="test content",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is True
        assert result.case_id == 42
        assert result.case_name == "Test Case"
        mock_cs.search_cases_by_case_number_internal.assert_not_called()

    def test_case_not_found(self):
        mock_cs = MagicMock()
        mock_cs.get_case_by_id_internal.return_value = None
        svc = CaseBindingService(case_service=mock_cs)

        result = svc.bind_document_to_case(
            case_id=99,
            document_type=DocumentType.SUMMONS,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is False
        assert result.error_code == "CASE_NOT_FOUND"

    def test_case_dto_none(self):
        mock_cs = MagicMock()
        mock_cs.get_case_by_id_internal.return_value = None

        svc = CaseBindingService(case_service=mock_cs)
        result = svc.bind_document_to_case(
            case_id=42,
            document_type=DocumentType.SUMMONS,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is False

    def test_success(self):
        mock_cs = MagicMock()
        mock_dto = MagicMock()
        mock_dto.name = "Test Case"
        mock_cs.get_case_by_id_internal.return_value = mock_dto
        mock_cs.create_case_log_internal.return_value = 200
        mock_cs.add_case_log_attachment_internal.return_value = True
        mock_cs.update_case_log_reminder_internal.return_value = True

        svc = CaseBindingService(case_service=mock_cs)
        svc.create_case_log = MagicMock(return_value=200)
        result = svc.bind_document_to_case(
            case_id=42,
            document_type=DocumentType.SUMMONS,
            content="test content",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is True
        assert result.case_id == 42
        assert result.case_name == "Test Case"
        mock_cs.update_case_log_reminder_internal.assert_not_called()

    def test_generic_exception(self):
        mock_cs = MagicMock()
        mock_dto = MagicMock()
        mock_dto.name = "Test"
        mock_cs.get_case_by_id_internal.return_value = mock_dto

        svc = CaseBindingService(case_service=mock_cs)
        svc.create_case_log = MagicMock(side_effect=RuntimeError("unexpected"))

        result = svc.bind_document_to_case(
            case_id=42,
            document_type=DocumentType.SUMMONS,
            content="test",
            file_path="/tmp/doc.pdf",
        )
        assert result.success is False
        assert result.error_code == "BINDING_ERROR"


class TestFormatLogContent:
    def test_summons_with_date_count(self):
        svc = CaseBindingService()
        result = svc.format_log_content(
            DocumentType.SUMMONS, "（2024）京01民初123号", "text", date_count=2
        )
        assert "传票" in result
        assert "案号" in result
        assert "识别到 2 个关键日期（待人工确认后写入重要日期提醒）" in result

    def test_execution_ruling_with_date_count(self):
        svc = CaseBindingService()
        result = svc.format_log_content(
            DocumentType.EXECUTION_RULING, None, "text", date_count=1
        )
        assert "执行裁定书" in result
        assert "识别到 1 个关键日期（待人工确认后写入重要日期提醒）" in result
        assert "案号" not in result

    def test_other_no_time(self):
        svc = CaseBindingService()
        result = svc.format_log_content(DocumentType.OTHER, None, "")
        assert "其他文书" in result
        assert "关键日期" not in result

    def test_long_text_truncated(self):
        svc = CaseBindingService()
        long_text = "x" * 600
        result = svc.format_log_content(DocumentType.OTHER, None, long_text)
        assert "..." in result

    def test_unknown_type_label(self):
        svc = CaseBindingService()
        result = svc.format_log_content("unknown_type", None, "text")  # type: ignore[arg-type]
        assert "法院文书" in result


class TestTriggerNotification:
    def test_notification_success(self):
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.renamed_file_path = "/tmp/renamed.pdf"
        mock_task.file_path = "/tmp/original.pdf"
        mock_task.case_number = "test"

        svc = CaseBindingService()

        mock_notif_svc = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.sent_at = datetime.now()
        mock_result.file_sent = True
        mock_result.message = "ok"
        mock_notif_svc.send_notification.return_value = mock_result

        # Patch the local import inside _trigger_notification
        with patch.dict("sys.modules", {"apps.document_recognition.services.notification_service": MagicMock(
            DocumentRecognitionNotificationService=MagicMock(return_value=mock_notif_svc)
        )}):
            svc._trigger_notification(mock_task, 1, "Test Case", DocumentType.SUMMONS)

        assert mock_task.notification_sent is True
        assert mock_task.notification_file_sent is True
        mock_task.save.assert_called()

    def test_notification_failure(self):
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.renamed_file_path = None
        mock_task.file_path = "/tmp/doc.pdf"

        svc = CaseBindingService()

        mock_notif_svc = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.sent_at = None
        mock_result.file_sent = False
        mock_result.message = "send failed"
        mock_result.error_code = "SEND_ERROR"
        mock_notif_svc.send_notification.return_value = mock_result

        with patch.dict("sys.modules", {"apps.document_recognition.services.notification_service": MagicMock(
            DocumentRecognitionNotificationService=MagicMock(return_value=mock_notif_svc)
        )}):
            svc._trigger_notification(mock_task, 1, "Test Case", DocumentType.SUMMONS)

        assert mock_task.notification_sent is False
        assert mock_task.notification_error == "send failed"

    def test_notification_exception(self):
        mock_task = MagicMock()
        mock_task.id = 1

        svc = CaseBindingService()
        # Force an exception during notification
        mock_notif_mod = MagicMock()
        mock_notif_mod.DocumentRecognitionNotificationService.side_effect = Exception("import error")

        with patch.dict("sys.modules", {"apps.document_recognition.services.notification_service": mock_notif_mod}):
            svc._trigger_notification(mock_task, 1, "Test Case", DocumentType.SUMMONS)

        assert mock_task.notification_sent is False
