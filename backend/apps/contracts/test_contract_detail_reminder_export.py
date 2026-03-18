"""Regression tests for contract detail reminder export path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.contracts.admin.mixins.display_mixin import _get_contract_detail_reminders
from apps.core.interfaces import ServiceLocator
from apps.reminders.models import ReminderType
from apps.testing.factories import ContractFactory


class _ReminderServiceExportFake:
    def __init__(self, exported: list[dict[str, Any]]) -> None:
        self.exported = exported
        self.calls: list[int] = []

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]:
        self.calls.append(contract_id)
        return self.exported


@pytest.mark.django_db
def test_contract_detail_uses_reminder_service_export(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = ContractFactory(name="detail-export")
    due_at = datetime.now(tz=UTC) + timedelta(days=1)
    fake = _ReminderServiceExportFake(
        exported=[
            {
                "id": 1,
                "contract_id": contract.id,
                "case_log_id": None,
                "reminder_type": ReminderType.HEARING.value,
                "reminder_type_label": "开庭",
                "content": "from-service",
                "due_at": due_at,
                "metadata": {"source": "svc"},
            }
        ]
    )
    monkeypatch.setattr(ServiceLocator, "get_reminder_service", classmethod(lambda cls: fake))

    reminders = _get_contract_detail_reminders(contract)

    assert fake.calls == [contract.id]
    assert reminders[0]["content"] == "from-service"
    assert reminders[0]["due_at"] == due_at
    assert reminders[0]["reminder_type_label"] == "开庭"
