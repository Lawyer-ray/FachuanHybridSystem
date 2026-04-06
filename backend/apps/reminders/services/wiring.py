"""Dependency injection wiring for reminders module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reminder_service_adapter import ReminderServiceAdapter


def get_reminder_service() -> ReminderServiceAdapter:
    """获取 ReminderServiceAdapter 实例（供本模块 API 和其他模块使用）。"""
    from apps.cases.adapters import CaseLogReminderTargetQueryAdapter, CaseReminderTargetQueryAdapter
    from apps.contracts.adapters import ContractReminderTargetQueryAdapter

    from .reminder_service_adapter import ReminderServiceAdapter

    return ReminderServiceAdapter(
        contract_target_query=ContractReminderTargetQueryAdapter(),
        case_target_query=CaseReminderTargetQueryAdapter(),
        case_log_target_query=CaseLogReminderTargetQueryAdapter(),
    )
