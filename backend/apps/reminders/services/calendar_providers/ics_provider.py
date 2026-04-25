"""ICS file parser provider using the icalendar library."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from icalendar import Calendar

from .base import CalendarEvent, CalendarEventProvider

logger = logging.getLogger(__name__)


class IcsFileProvider:
    """Parse .ics file content into CalendarEvent objects."""

    def fetch_events(self, *, ics_content: bytes, **kwargs: object) -> list[CalendarEvent]:
        """Parse .ics bytes and return a list of CalendarEvent."""
        try:
            cal = Calendar.from_ical(ics_content)
        except Exception:
            logger.info("ICS parse failed: invalid .ics content")
            return []

        events: list[CalendarEvent] = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            event = self._parse_vevent(component)
            if event is not None:
                events.append(event)

        return events

    def _parse_vevent(self, component: object) -> CalendarEvent | None:
        """Convert a VEVENT component to CalendarEvent."""
        vevent = component  # icalendar component
        summary = self._get_str(vevent, "SUMMARY")
        if not summary:
            return None

        uid = self._get_str(vevent, "UID") or ""

        start_val = vevent.get("DTSTART")
        end_val = vevent.get("DTEND")

        start_dt, is_all_day = self._parse_dt(start_val)
        end_dt, _ = self._parse_dt(end_val)

        location = self._get_str(vevent, "LOCATION") or ""
        description = self._get_str(vevent, "DESCRIPTION") or ""
        organizer = self._parse_organizer(vevent.get("ORGANIZER"))

        return CalendarEvent(
            uid=uid,
            title=summary,
            start_dt=start_dt,
            end_dt=end_dt,
            location=location,
            description=description,
            organizer=organizer,
            is_all_day=is_all_day,
        )

    @staticmethod
    def _get_str(vevent: object, key: str) -> str:
        """Safely get a string property from a vevent component."""
        val = vevent.get(key)
        if val is None:
            return ""
        if isinstance(val, list):
            return str(val[0]) if val else ""
        return str(val)

    @staticmethod
    def _parse_dt(dt_val: object) -> tuple[datetime | None, bool]:
        """Parse a DTSTART/DTEND value into (datetime, is_all_day)."""
        if dt_val is None:
            return None, False

        # icalendar returns vDDDTypes
        actual = dt_val.dt if hasattr(dt_val, "dt") else dt_val

        if isinstance(actual, datetime):
            if actual.tzinfo is None:
                actual = actual.replace(tzinfo=UTC)
            return actual, False

        if isinstance(actual, date):
            # All-day event — store as midnight UTC
            dt = datetime(actual.year, actual.month, actual.day, tzinfo=UTC)
            return dt, True

        return None, False

    @staticmethod
    def _parse_organizer(org: object) -> str:
        """Extract organizer display name or email."""
        if org is None:
            return ""
        if hasattr(org, "params"):
            cn = org.params.get("CN")
            if cn:
                return str(cn)
        val = str(org)
        if val.startswith("MAILTO:"):
            return val[7:]
        return val
