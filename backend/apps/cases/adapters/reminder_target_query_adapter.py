"""Reminder target query adapters for cases."""

from __future__ import annotations

from apps.cases.models import CaseLog
from apps.reminders.ports import CaseLogTargetQueryPort


class CaseLogReminderTargetQueryAdapter(CaseLogTargetQueryPort):
    """Case log existence lookup for reminders module."""

    def exists(self, case_log_id: int) -> bool:
        return CaseLog.objects.filter(id=case_log_id).exists()
