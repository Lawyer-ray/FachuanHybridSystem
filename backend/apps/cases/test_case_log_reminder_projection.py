"""Regression tests for CaseLog reminder projection properties."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.core.interfaces import ServiceLocator
from apps.reminders.models import ReminderType
from apps.testing.factories import CaseLogFactory


class _ReminderServiceProjectionFake:
    def __init__(self, exported: list[dict[str, Any]], latest: dict[str, Any] | None) -> None:
        self.exported = exported
        self.latest = latest
        self.export_calls: list[int] = []
        self.latest_calls: list[int] = []

    def export_case_log_reminders_internal(self, *, case_log_id: int) -> list[dict[str, Any]]:
        self.export_calls.append(case_log_id)
        return self.exported

    def get_latest_case_log_reminder_internal(self, *, case_log_id: int) -> dict[str, Any] | None:
        self.latest_calls.append(case_log_id)
        return self.latest


class _LegacyReminderServiceFake:
    pass


class _ReminderServiceLatestRaisesFake:
    def __init__(self, exported: list[dict[str, Any]]) -> None:
        self.exported = exported
        self.export_calls: list[int] = []
        self.latest_calls: list[int] = []

    def export_case_log_reminders_internal(self, *, case_log_id: int) -> list[dict[str, Any]]:
        self.export_calls.append(case_log_id)
        return self.exported

    def get_latest_case_log_reminder_internal(self, *, case_log_id: int) -> dict[str, Any] | None:
        self.latest_calls.append(case_log_id)
        raise RuntimeError("boom")


@pytest.mark.django_db
def test_case_log_projection_uses_reminder_service(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CaseLogFactory()
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    exported = [
        {
            "id": 1,
            "contract_id": None,
            "case_log_id": log.id,
            "reminder_type": ReminderType.HEARING.value,
            "reminder_type_label": "开庭",
            "content": "from-service",
            "due_at": due_at,
            "metadata": {"source": "svc"},
        }
    ]
    fake = _ReminderServiceProjectionFake(exported=exported, latest=exported[0])
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    assert log.reminder_entries == exported
    assert log.has_reminders is True
    assert log.reminder_count == 1
    assert log.reminder_type == ReminderType.HEARING.value
    assert log.reminder_time == due_at
    assert fake.export_calls == [log.id]
    assert fake.latest_calls == [log.id]


@pytest.mark.django_db
def test_case_log_projection_returns_empty_when_service_missing_export_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = CaseLogFactory()
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: _LegacyReminderServiceFake()))

    assert log.has_reminders is False
    assert log.reminder_count == 0
    assert log.reminder_entries == []
    assert log.reminder_type is None
    assert log.reminder_time is None


@pytest.mark.django_db
def test_case_log_projection_falls_back_to_exported_when_latest_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = CaseLogFactory()
    exported = [
        {"reminder_type": ReminderType.HEARING.value, "due_at": None},
        {"reminder_type": ReminderType.OTHER.value, "due_at": None},
    ]
    fake = _ReminderServiceLatestRaisesFake(exported=exported)
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    assert log.reminder_type == ReminderType.OTHER.value
    assert log.reminder_count == 2
    assert fake.latest_calls == [log.id]
    assert fake.export_calls == [log.id]
