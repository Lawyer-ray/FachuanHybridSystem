"""Calendar export service — export Reminder records to .ics format."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone
from icalendar import Alarm, Event, vDatetime, vText

from ..models import Reminder, ReminderType

logger = logging.getLogger(__name__)


class CalendarExportService:
    """Export Reminder records to .ics file format."""

    def export_reminders(
        self,
        *,
        year: int,
        month: int,
        reminder_type: str = "",
        scope: str = "all",
        status: str = "all",
    ) -> bytes:
        """Query matching Reminders and return .ics file bytes."""
        reminders = self._query_reminders(
            year=year,
            month=month,
            reminder_type=reminder_type,
            scope=scope,
            status=status,
        )

        from icalendar import Calendar

        cal = Calendar()
        cal.add("prodid", "-//法穿AI Copilot//Reminder Export//CN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "法穿提醒")
        cal.add("x-wr-timezone", "Asia/Shanghai")

        for reminder in reminders:
            vevent = self._reminder_to_vevent(reminder)
            if vevent is not None:
                cal.add_component(vevent)

        return bytes(cal.to_ical())

    def _query_reminders(
        self,
        *,
        year: int,
        month: int,
        reminder_type: str,
        scope: str,
        status: str,
    ) -> list[Reminder]:
        """Query reminders matching the given filters."""
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        next_month_start = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)

        queryset = Reminder.objects.select_related(
            "contract", "case", "case_log", "case_log__case"
        ).filter(
            due_at__date__gte=month_start,
            due_at__date__lt=next_month_start,
        )

        valid_types = {value for value, _ in ReminderType.choices}
        if reminder_type in valid_types:
            queryset = queryset.filter(reminder_type=reminder_type)

        if scope == "contract":
            queryset = queryset.filter(contract_id__isnull=False)
        elif scope == "case":
            queryset = queryset.filter(case_id__isnull=False)
        elif scope == "case_log":
            queryset = queryset.filter(case_log_id__isnull=False)

        now = timezone.now()
        if status == "overdue":
            queryset = queryset.filter(due_at__lt=now)
        elif status == "upcoming":
            queryset = queryset.filter(due_at__gte=now)

        return list(queryset.order_by("due_at", "id"))

    @staticmethod
    def _reminder_to_vevent(reminder: Reminder) -> Event | None:
        """Convert a Reminder to an iCal VEVENT component."""
        if not reminder.due_at:
            return None

        vevent = Event()
        vevent.add("uid", f"reminder-{reminder.id}@fachuan-system")
        vevent.add("summary", reminder.content)

        # DTSTART
        due_local = timezone.localtime(reminder.due_at)
        vevent.add("dtstart", due_local)

        # DTEND = DTSTART + 1 hour (default duration)
        metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
        end_at = metadata.get("end_at")
        if end_at:
            try:
                end_dt = datetime.fromisoformat(str(end_at))
                if end_dt.tzinfo is None:
                    end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
                vevent.add("dtend", timezone.localtime(end_dt))
            except (ValueError, TypeError):
                vevent.add("dtend", due_local + timedelta(hours=1))
        else:
            vevent.add("dtend", due_local + timedelta(hours=1))

        # CATEGORIES
        type_label = dict(ReminderType.choices).get(reminder.reminder_type, reminder.reminder_type)
        vevent.add("categories", str(type_label))

        # LOCATION
        location = metadata.get("courtroom", "") or metadata.get("location", "")
        if location and location != "missing value":
            vevent.add("location", str(location))

        # DESCRIPTION
        desc_parts: list[str] = []
        if reminder.contract_id is not None and reminder.contract:
            desc_parts.append(f"合同: {reminder.contract.name}")
        if reminder.case_id is not None and reminder.case:
            desc_parts.append(f"案件: {reminder.case.name}")
        if reminder.case_log_id is not None and reminder.case_log:
            desc_parts.append(f"案件日志: #{reminder.case_log_id}")
        note = metadata.get("note", "")
        if note:
            desc_parts.append(f"备注: {note}")
        if desc_parts:
            vevent.add("description", "\n".join(desc_parts))

        # STATUS
        vevent.add("status", "CONFIRMED")

        # DTSTAMP
        vevent.add("dtstamp", timezone.now())

        return vevent
