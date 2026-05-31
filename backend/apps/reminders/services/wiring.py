"""Dependency injection wiring for reminders module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .calendar_export_service import CalendarExportService
    from .calendar_sync_service import CalendarSyncService
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

def get_calendar_sync_service() -> CalendarSyncService:
    """获取 CalendarSyncService 实例（日历导入功能）。"""
    from .calendar_sync_service import CalendarSyncService

    return CalendarSyncService()

def get_calendar_export_service() -> CalendarExportService:
    """获取 CalendarExportService 实例（日历导出功能）。"""
    from .calendar_export_service import CalendarExportService

    return CalendarExportService()
