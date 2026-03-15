"""Regression tests for contract admin reminder export path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.contracts.admin.contract_admin import serialize_contract_obj
from apps.core.interfaces import ServiceLocator
from apps.reminders.models import ReminderType
from tests.factories import ContractFactory


class _ReminderServiceExportFake:
    def __init__(self, exported: list[dict[str, Any]]) -> None:
        self.exported = exported
        self.calls: list[int] = []

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]:
        self.calls.append(contract_id)
        return self.exported


@pytest.mark.django_db
def test_serialize_contract_obj_uses_reminder_service_export(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = ContractFactory(name="contract-export")
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    fake = _ReminderServiceExportFake(
        exported=[{
            "reminder_type": ReminderType.HEARING.value,
            "content": "from-service",
            "due_at": due_at,
            "metadata": {"source": "svc"},
        }]
    )
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    data = serialize_contract_obj(contract)

    assert fake.calls == [contract.id]
    assert data["reminders"][0]["content"] == "from-service"
    assert data["reminders"][0]["due_at"] == due_at.isoformat()
