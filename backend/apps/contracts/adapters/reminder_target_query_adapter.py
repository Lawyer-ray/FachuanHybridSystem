"""Reminder target query adapters for contracts."""

from __future__ import annotations

from apps.contracts.models import Contract
from apps.reminders.ports import ContractTargetQueryPort


class ContractReminderTargetQueryAdapter(ContractTargetQueryPort):
    """Contract existence lookup for reminders module."""

    def exists(self, contract_id: int) -> bool:
        return Contract.objects.filter(id=contract_id).exists()
