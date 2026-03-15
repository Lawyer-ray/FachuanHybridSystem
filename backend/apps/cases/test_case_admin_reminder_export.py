"""Regression tests for case admin reminder export path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.cases.admin.case_admin import serialize_case_obj
from apps.core.interfaces import ServiceLocator
from apps.reminders.models import ReminderType
from tests.factories import CaseFactory, CaseLogFactory


class _ReminderServiceBatchFake:
    def __init__(self, exported: dict[int, list[dict[str, Any]]]) -> None:
        self.exported = exported
        self.calls: list[list[int]] = []

    def export_case_log_reminders_batch_internal(self, *, case_log_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        self.calls.append(case_log_ids)
        return self.exported


@pytest.mark.django_db
def test_serialize_case_obj_uses_reminder_service_batch_export(monkeypatch: pytest.MonkeyPatch) -> None:
    case = CaseFactory(name="case-export")
    first_log = CaseLogFactory(case=case, content="log-1")
    second_log = CaseLogFactory(case=case, content="log-2")
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    fake = _ReminderServiceBatchFake(
        exported={
            first_log.id: [{
                "reminder_type": ReminderType.HEARING.value,
                "content": "from-service-1",
                "due_at": due_at,
                "metadata": {"source": "svc"},
            }],
            second_log.id: [{
                "reminder_type": ReminderType.OTHER.value,
                "content": "from-service-2",
                "due_at": due_at + timedelta(hours=1),
                "metadata": {"source": "svc"},
            }],
        }
    )
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    data = serialize_case_obj(case)

    assert fake.calls == [[first_log.id, second_log.id]]
    logs_by_content = {item["content"]: item for item in data["logs"]}
    assert logs_by_content["log-1"]["reminders"][0]["content"] == "from-service-1"
    assert logs_by_content["log-1"]["reminders"][0]["due_at"] == due_at.isoformat()
    assert logs_by_content["log-2"]["reminders"][0]["content"] == "from-service-2"
