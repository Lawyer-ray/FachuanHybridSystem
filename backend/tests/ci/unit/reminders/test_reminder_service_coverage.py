"""reminders/services/reminder_service.py 单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.services.reminder_service import ReminderService


def _mock_target_query() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service() -> ReminderService:
    return ReminderService(
        contract_target_query=_mock_target_query(),
        case_target_query=_mock_target_query(),
        case_log_target_query=_mock_target_query(),
    )


# ── list_reminders ─────────────────────────────────────────────────────


class TestListReminders:
    def test_multiple_filters_raises(self, service: ReminderService) -> None:
        with pytest.raises(ValidationException):
            service.list_reminders(contract_id=1, case_id=2)

    def test_no_filters(self, service: ReminderService) -> None:
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            qs = MagicMock()
            MockReminder.objects.order_by.return_value = qs
            result = service.list_reminders()
            MockReminder.objects.order_by.assert_called_once_with("-due_at", "-id")

    def test_contract_filter(self, service: ReminderService) -> None:
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            qs = MagicMock()
            MockReminder.objects.order_by.return_value = qs
            service.list_reminders(contract_id=5)
            qs.filter.assert_called_once_with(contract_id=5)

    def test_case_filter(self, service: ReminderService) -> None:
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            qs = MagicMock()
            MockReminder.objects.order_by.return_value = qs
            service.list_reminders(case_id=10)
            qs.filter.assert_called_once_with(case_id=10)

    def test_case_log_filter(self, service: ReminderService) -> None:
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            qs = MagicMock()
            MockReminder.objects.order_by.return_value = qs
            service.list_reminders(case_log_id=3)
            qs.filter.assert_called_once_with(case_log_id=3)


# ── get_reminder ───────────────────────────────────────────────────────


class TestGetReminder:
    def test_not_found(self, service: ReminderService) -> None:
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            MockReminder.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockReminder.objects.get.side_effect = MockReminder.DoesNotExist()
            with pytest.raises(NotFoundError):
                service.get_reminder(999)

    def test_found(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(id=1)
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            MockReminder.objects.get.return_value = reminder
            assert service.get_reminder(1) is reminder

    def test_select_related(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(id=1)
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            MockReminder.objects.select_related.return_value.get.return_value = reminder
            result = service.get_reminder(1, select_related=True)
            assert result is reminder


# ── update_reminder ────────────────────────────────────────────────────


class TestUpdateReminder:
    def test_with_changes(self, service: ReminderService, db: object) -> None:
        reminder = SimpleNamespace(
            id=1,
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="evidence_deadline",
            content="old",
            metadata={},
            due_at=datetime.now(),
            save=MagicMock(),
        )
        with patch.object(service, "get_reminder", return_value=reminder):
            result = service.update_reminder(1, {"content": "new content", "reminder_type": "appeal_deadline"})
            reminder.save.assert_called_once()
            assert "updated_at" in reminder.save.call_args[1]["update_fields"]

    def test_no_changes(self, service: ReminderService, db: object) -> None:
        reminder = SimpleNamespace(
            id=1,
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="evidence_deadline",
            content="test",
            metadata={},
            due_at=datetime.now(),
            save=MagicMock(),
        )
        with patch.object(service, "get_reminder", return_value=reminder):
            service.update_reminder(1, {})
            reminder.save.assert_not_called()


# ── delete_reminder ────────────────────────────────────────────────────


class TestDeleteReminder:
    def test_success(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(id=1, delete=MagicMock(return_value=(1, {})))
        with patch.object(service, "get_reminder", return_value=reminder), \
             patch("django.db.transaction.atomic", MagicMock()):
            service.delete_reminder(1)
            reminder.delete.assert_called_once()


# ── _apply_update_fields ───────────────────────────────────────────────


class TestApplyUpdateFields:
    def test_enum_reminder_type(self, service: ReminderService) -> None:
        class FakeType:
            value = "evidence_deadline"

        reminder = SimpleNamespace(
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="old_type",
            content="c",
            metadata={},
            due_at=datetime.now(),
        )
        changed = service._apply_update_fields(reminder, {"reminder_type": FakeType()})
        assert "reminder_type" in changed

    def test_due_at_change(self, service: ReminderService) -> None:
        now = datetime.now()
        reminder = SimpleNamespace(
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="deadline",
            content="c",
            metadata={},
            due_at=now,
        )
        new_time = now + timedelta(days=1)
        changed = service._apply_update_fields(reminder, {"due_at": new_time})
        assert "due_at" in changed

    def test_metadata_change(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="deadline",
            content="c",
            metadata={},
            due_at=datetime.now(),
        )
        changed = service._apply_update_fields(reminder, {"metadata": {"key": "val"}})
        assert "metadata" in changed

    def test_fk_change_validates(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="deadline",
            content="c",
            metadata={},
            due_at=datetime.now(),
        )
        changed = service._apply_update_fields(reminder, {"contract_id": 5})
        assert "contract_id" in changed

    def test_fk_exclusive_validation(self, service: ReminderService) -> None:
        reminder = SimpleNamespace(
            contract_id=None,
            case_id=None,
            case_log_id=None,
            reminder_type="deadline",
            content="c",
            metadata={},
            due_at=datetime.now(),
        )
        with pytest.raises(ValidationException):
            service._apply_update_fields(reminder, {"contract_id": 1, "case_id": 2})


# ── get_existing_due_times ─────────────────────────────────────────────


class TestGetExistingDueTimes:
    def test_empty_case_log_id_raises(self, service: ReminderService) -> None:
        with pytest.raises(ValidationException):
            service.get_existing_due_times(0, "deadline")

    def test_returns_set(self, service: ReminderService) -> None:
        now = datetime.now()
        with patch("apps.reminders.services.reminder_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value.flat = [now]
            MockReminder.objects.filter.return_value.values_list.return_value = [now]
            result = service.get_existing_due_times(1, "deadline")
            assert isinstance(result, set)
