from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.cases.services.log.caselog_service import CaseLogService
from apps.reminders.models import Reminder
from apps.reminders.services.reminder_service_adapter import CASE_LOG_API_REMINDER_SOURCE


@pytest.mark.django_db
def test_create_log_with_reminder_creates_api_managed_reminder(case: object, lawyer: object) -> None:
    service = CaseLogService()
    due_at = datetime.now(tz=UTC) + timedelta(days=3)

    log = service.create_log(
        case_id=case.id,
        content="创建日志并提醒",
        user=lawyer,
        perm_open_access=True,
        reminder_type="hearing",
        reminder_time=due_at,
    )

    reminders = list(Reminder.objects.filter(case_log_id=log.id))
    assert len(reminders) == 1
    assert reminders[0].reminder_type == "hearing"
    assert reminders[0].content == "创建日志并提醒"
    assert reminders[0].metadata.get("source") == CASE_LOG_API_REMINDER_SOURCE


@pytest.mark.django_db
def test_update_log_with_reminder_fields_updates_existing_api_managed_reminder(case: object, lawyer: object) -> None:
    service = CaseLogService()
    initial_due_at = datetime.now(tz=UTC) + timedelta(days=1)
    updated_due_at = initial_due_at + timedelta(days=2)

    log = service.create_log(
        case_id=case.id,
        content="首次内容",
        user=lawyer,
        perm_open_access=True,
        reminder_type="hearing",
        reminder_time=initial_due_at,
    )

    service.update_log(
        log_id=log.id,
        data={
            "content": "更新后的内容",
            "reminder_type": "payment_deadline",
            "reminder_time": updated_due_at,
        },
        user=lawyer,
        perm_open_access=True,
    )

    reminders = list(Reminder.objects.filter(case_log_id=log.id))
    assert len(reminders) == 1
    assert reminders[0].reminder_type == "payment_deadline"
    assert reminders[0].content == "更新后的内容"
    assert reminders[0].due_at == updated_due_at
    assert reminders[0].metadata.get("source") == CASE_LOG_API_REMINDER_SOURCE


@pytest.mark.django_db
def test_update_log_with_null_reminder_fields_clears_only_api_managed_reminder(case: object, lawyer: object) -> None:
    service = CaseLogService()
    due_at = datetime.now(tz=UTC) + timedelta(days=1)

    log = service.create_log(
        case_id=case.id,
        content="带提醒的日志",
        user=lawyer,
        perm_open_access=True,
        reminder_type="hearing",
        reminder_time=due_at,
    )

    other_reminder = Reminder.objects.create(
        case_log_id=log.id,
        reminder_type="other",
        content="外部来源提醒",
        due_at=due_at + timedelta(hours=1),
        metadata={"source": "external"},
    )

    service.update_log(
        log_id=log.id,
        data={"reminder_type": None, "reminder_time": None},
        user=lawyer,
        perm_open_access=True,
    )

    reminders = list(Reminder.objects.filter(case_log_id=log.id))
    assert len(reminders) == 1
    assert reminders[0].id == other_reminder.id
    assert reminders[0].metadata.get("source") == "external"
