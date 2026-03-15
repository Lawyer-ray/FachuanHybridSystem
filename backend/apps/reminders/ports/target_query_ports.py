"""Target existence query ports used by reminders write service."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ContractTargetQueryPort(Protocol):
    """Query contract target existence for reminder binding."""

    def exists(self, contract_id: int) -> bool: ...


@runtime_checkable
class CaseLogTargetQueryPort(Protocol):
    """Query case log target existence for reminder binding."""

    def exists(self, case_log_id: int) -> bool: ...
