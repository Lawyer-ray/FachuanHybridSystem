"""Regression tests for contract clone workflow reminder export path."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from dateutil.relativedelta import relativedelta

from apps.contracts.models import Contract
from apps.contracts.services.contract.admin_workflows import ContractCloneWorkflow
from apps.reminders.models import Reminder
from tests.factories import ContractFactory


class _ReminderServiceFake:
    def __init__(self, exported_reminders: list[dict[str, Any]]) -> None:
        self.exported_reminders = exported_reminders
        self.export_calls: list[int] = []
        self.create_calls: list[dict[str, Any]] = []

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]:
        self.export_calls.append(contract_id)
        return self.exported_reminders

    def create_contract_reminders_internal(self, *, contract_id: int, reminders: list[dict[str, Any]]) -> int:
        self.create_calls.append({"contract_id": contract_id, "reminders": reminders})
        for item in reminders:
            Reminder.objects.create(
                contract_id=contract_id,
                reminder_type=item["reminder_type"],
                content=item["content"],
                due_at=item["due_at"],
                metadata=item["metadata"],
            )
        return len(reminders)


@pytest.mark.django_db
def test_clone_workflow_uses_reminder_service_export_path() -> None:
    source_contract: Contract = ContractFactory(name="source")
    target_contract: Contract = ContractFactory(name="target")
    due_at = datetime(2026, 5, 1, tzinfo=UTC)
    fake = _ReminderServiceFake(
        exported_reminders=[{
            "reminder_type": "hearing",
            "content": "exported reminder",
            "due_at": due_at,
            "metadata": {"from": "export"},
        }]
    )
    workflow = ContractCloneWorkflow(reminder_service=fake)

    workflow.clone_related_data(source_contract=source_contract, target_contract=target_contract)

    assert fake.export_calls == [source_contract.id]
    assert len(fake.create_calls) == 1
    assert Reminder.objects.filter(contract_id=target_contract.id).count() == 1
    cloned = Reminder.objects.get(contract_id=target_contract.id)
    assert cloned.content == "exported reminder"
    assert cloned.due_at == due_at


@pytest.mark.django_db
def test_clone_workflow_applies_due_at_transform_to_exported_reminders() -> None:
    source_contract: Contract = ContractFactory(name="source")
    target_contract: Contract = ContractFactory(name="target")
    due_at = datetime(2026, 5, 1, tzinfo=UTC)
    fake = _ReminderServiceFake(
        exported_reminders=[{
            "reminder_type": "hearing",
            "content": "exported reminder",
            "due_at": due_at,
            "metadata": {"from": "export"},
        }]
    )
    workflow = ContractCloneWorkflow(reminder_service=fake)

    workflow.clone_related_data(
        source_contract=source_contract,
        target_contract=target_contract,
        due_at_transform=ContractCloneWorkflow.plus_one_year_due_at,
    )

    assert fake.export_calls == [source_contract.id]
    assert len(fake.create_calls) == 1
    reminders = fake.create_calls[0]["reminders"]
    assert reminders[0]["due_at"] == due_at + relativedelta(years=1)
