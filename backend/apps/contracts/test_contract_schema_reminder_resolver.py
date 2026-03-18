"""Regression tests for ContractOut reminder resolver."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.contracts.schemas.contract_schemas import ContractOut
from apps.core.interfaces import ServiceLocator
from apps.testing.factories import ContractFactory


class _ReminderServiceExportFake:
    def __init__(self, exported: list[dict[str, Any]]) -> None:
        self.exported = exported
        self.calls: list[int] = []

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]:
        self.calls.append(contract_id)
        return self.exported


@pytest.mark.django_db
def test_contract_out_resolve_reminders_uses_service_export(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = ContractFactory()
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    fake = _ReminderServiceExportFake(
        exported=[
            {
                "id": 1,
                "contract_id": contract.id,
                "case_log_id": None,
                "reminder_type": "hearing",
                "reminder_type_label": "开庭",
                "content": "from-service",
                "due_at": due_at,
                "metadata": {"source": "svc"},
            }
        ]
    )
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    reminders = ContractOut.resolve_reminders(contract)

    assert fake.calls == [contract.id]
    assert isinstance(reminders, list)
    assert reminders[0]["content"] == "from-service"
