"""Reminder target query adapters for cases."""

from __future__ import annotations

from apps.cases.models import Case, CaseLog
from apps.reminders.ports import CaseLogTargetQueryPort, CaseTargetQueryPort


class CaseReminderTargetQueryAdapter(CaseTargetQueryPort):
    """Case existence lookup for reminders module."""

    def exists(self, case_id: int) -> bool:
        return bool(Case.objects.filter(id=case_id).exists())


class CaseLogReminderTargetQueryAdapter(CaseLogTargetQueryPort):
    """Case log existence lookup for reminders module."""

    def exists(self, case_log_id: int) -> bool:
        return bool(CaseLog.objects.filter(id=case_log_id).exists())
