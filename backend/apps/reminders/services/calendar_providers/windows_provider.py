"""Windows Outlook provider via pywin32 COM automation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from .base import CalendarEvent

logger = logging.getLogger(__name__)


class WindowsOutlookProvider:
    """Read events from local Outlook via COM automation."""

    def fetch_events(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        **kwargs: object,
    ) -> list[CalendarEvent]:
        """Fetch events from Outlook Calendar within the date range."""
        try:
            import win32com.client  # type: ignore[import-untyped,unused-ignore]
        except ImportError:
            logger.info("pywin32 not available, Windows Outlook sync disabled")
            return []

        now = timezone.now()
        if start_date is None:
            start_date = now - timedelta(days=90)
        if end_date is None:
            end_date = now + timedelta(days=180)

        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            calendar_folder = namespace.GetDefaultFolder(9)  # olFolderCalendar
        except Exception as exc:
            logger.info("Outlook COM access failed: %s", exc)
            return []

        events: list[CalendarEvent] = []
        try:
            items = calendar_folder.Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True

            start_str = start_date.strftime("%m/%d/%Y %H:%M %p")
            end_str = end_date.strftime("%m/%d/%Y %H:%M %p")
            filter_str = f"[Start] >= '{start_str}' AND [End] <= '{end_str}'"
            filtered = items.Restrict(filter_str)

            for item in filtered:
                event = self._convert_event(item)
                if event is not None:
                    events.append(event)
        except Exception as exc:
            logger.info("Outlook Calendar read failed: %s", exc)

        return events

    @staticmethod
    def _convert_event(item: Any) -> CalendarEvent | None:
        """Convert an Outlook COM item to CalendarEvent."""
        try:
            title = getattr(item, "Subject", "") or ""
            if not title:
                return None

            start_dt = getattr(item, "Start", None)
            end_dt = getattr(item, "End", None)
            uid = getattr(item, "EntryID", "") or ""
            location = getattr(item, "Location", "") or ""
            body = getattr(item, "Body", "") or ""
            organizer = getattr(item, "Organizer", "") or ""
            is_all_day = getattr(item, "AllDayEvent", False)

            # Outlook returns pywintypes.datetime; convert to stdlib datetime
            if start_dt is not None and not isinstance(start_dt, datetime):
                try:
                    start_dt = datetime(
                        start_dt.year, start_dt.month, start_dt.day,
                        start_dt.hour, start_dt.minute, start_dt.second,
                        tzinfo=timezone.get_current_timezone(),
                    )
                except Exception:
                    start_dt = None

            if end_dt is not None and not isinstance(end_dt, datetime):
                try:
                    end_dt = datetime(
                        end_dt.year, end_dt.month, end_dt.day,
                        end_dt.hour, end_dt.minute, end_dt.second,
                        tzinfo=timezone.get_current_timezone(),
                    )
                except Exception:
                    end_dt = None

            return CalendarEvent(
                uid=str(uid),
                title=str(title),
                start_dt=start_dt,
                end_dt=end_dt,
                location=str(location),
                description=str(body),
                organizer=str(organizer),
                is_all_day=bool(is_all_day),
            )
        except Exception as exc:
            logger.info("Outlook event conversion failed: %s", exc)
            return None
