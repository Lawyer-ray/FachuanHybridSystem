"""Regression tests for CaseLogOut reminder resolver."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.cases.schemas.log_schemas import CaseLogOut
from apps.core.interfaces import ServiceLocator
from tests.factories import CaseLogFactory


class _ReminderServiceExportFake:
    def __init__(self, exported: list[dict[str, object]]) -> None:
        self.exported = exported
        self.calls: list[int] = []

    def export_case_log_reminders_internal(self, *, case_log_id: int) -> list[dict[str, object]]:
        self.calls.append(case_log_id)
        return self.exported


@pytest.mark.django_db
def test_case_log_out_resolve_reminders_uses_service_export(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CaseLogFactory()
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    fake = _ReminderServiceExportFake(
        exported=[{
            "id": 1,
            "contract_id": None,
            "case_log_id": log.id,
            "reminder_type": "hearing",
            "reminder_type_label": "开庭",
            "content": "from-service",
            "due_at": due_at,
            "metadata": {"source": "svc"},
        }]
    )
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    reminders = CaseLogOut.resolve_reminders(log)

    assert fake.calls == [log.id]
    assert isinstance(reminders, list)
    assert reminders[0]["content"] == "from-service"
