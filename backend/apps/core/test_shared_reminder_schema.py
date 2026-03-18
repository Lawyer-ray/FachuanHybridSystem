"""Regression tests for shared reminder schema usage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.cases.schemas.base import ReminderOut as CaseReminderOut
from apps.contracts.schemas.contract_schemas import ReminderOut as ContractReminderOut
from apps.core.api.schemas_shared import ReminderLiteOut
from apps.reminders.models import Reminder, ReminderType
from apps.reminders.schemas import ReminderOut as LegacyReminderOut
from apps.testing.factories import ContractFactory


@pytest.mark.django_db
def test_shared_reminder_schema_resolvers_keep_existing_output() -> None:
    contract = ContractFactory()
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    reminder = Reminder.objects.create(
        contract_id=contract.id,
        reminder_type=ReminderType.HEARING,
        content="shared-schema",
        due_at=due_at,
        metadata={"source": "test"},
    )

    assert ReminderLiteOut.resolve_reminder_type_label(reminder) == reminder.get_reminder_type_display()
    assert ReminderLiteOut.resolve_due_at(reminder) == LegacyReminderOut.resolve_due_at(reminder)
    assert ReminderLiteOut.resolve_created_at(reminder) == LegacyReminderOut.resolve_created_at(reminder)
    assert ReminderLiteOut.resolve_updated_at(reminder) == LegacyReminderOut.resolve_updated_at(reminder)


def test_case_and_contract_schemas_use_shared_reminder_schema() -> None:
    assert CaseReminderOut is ReminderLiteOut
    assert ContractReminderOut is ReminderLiteOut


def test_shared_reminder_schema_resolvers_support_export_dict() -> None:
    data = {
        "id": 1,
        "contract_id": 10,
        "case_log_id": None,
        "reminder_type": "hearing",
        "reminder_type_label": "开庭",
        "content": "dict-item",
        "metadata": {"source": "dict"},
        "due_at": "2026-03-20T10:00:00+08:00",
        "created_at": "2026-03-15T10:00:00+08:00",
        "updated_at": "2026-03-15T11:00:00+08:00",
    }

    assert ReminderLiteOut.resolve_reminder_type_label(data) == "开庭"
    assert ReminderLiteOut.resolve_due_at(data) == data["due_at"]
    assert ReminderLiteOut.resolve_created_at(data) == data["created_at"]
    assert ReminderLiteOut.resolve_updated_at(data) == data["updated_at"]
