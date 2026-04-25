"""macOS Calendar.app provider via AppleScript (osascript).

Uses AppleScript instead of EventKit because Python processes lack an app
bundle with NSCalendarsUsageDescription, so EventKit cannot trigger the
system permission dialog. osascript has a proper app identity and will
correctly prompt the user for Calendar access.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from .base import CalendarEvent

logger = logging.getLogger(__name__)

_OSASCRIPT = shutil.which("osascript") or "/usr/bin/osascript"


class MacCalendarProvider:
    """Read events from macOS Calendar.app using AppleScript."""

    # Calendar names that are typically subscription/holiday calendars (auto-excluded)
    DEFAULT_EXCLUDED_CALENDARS: list[str] = [
        "中国大陆节假日",
        "中国香港节假日",
        "中国澳门节假日",
        "US Holidays",
        "UK Holidays",
        "日本の祝日",
        "节假日",
        "Birthdays",
        "生日",
    ]

    def list_calendars(self) -> list[dict[str, str]]:
        """Return available calendar names and their types."""
        script = '''
tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set calName to name of cal
        set calType to ""
        try
            set calType to calendar type of cal as text
        end try
        set output to output & calName & "||" & calType & linefeed
    end repeat
    return output
end tell'''
        try:
            result = subprocess.run(
                [_OSASCRIPT, "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        if result.returncode != 0:
            return []

        calendars: list[dict[str, str]] = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("||")
            name = parts[0].strip() if parts else ""
            cal_type = parts[1].strip() if len(parts) > 1 else ""
            if name:
                calendars.append({"name": name, "type": cal_type})

        return calendars

    def fetch_events(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        excluded_calendars: list[str] | None = None,
        included_calendars: list[str] | None = None,
        **kwargs: object,
    ) -> list[CalendarEvent]:
        """Fetch events from macOS Calendar.app within the date range.

        Args:
            included_calendars: If provided, only query these calendars in
                AppleScript (much faster than querying all and filtering).
            excluded_calendars: Fallback — if included_calendars is not given,
                filter out these calendars in Python after the query.
        """
        now = timezone.now()
        if start_date is None:
            start_date = now - timedelta(days=90)
        if end_date is None:
            end_date = now + timedelta(days=180)

        # Determine which calendars to include in the AppleScript query
        if included_calendars is not None:
            # Preferred path: only query selected calendars in AppleScript
            script = self._build_script(start_date, end_date, included_calendars=included_calendars)
            do_python_filter = False
        else:
            # Legacy path: query all calendars, filter excluded ones in Python
            excluded = set(excluded_calendars or self.DEFAULT_EXCLUDED_CALENDARS)
            script = self._build_script(start_date, end_date)
            do_python_filter = bool(excluded)

        try:
            result = subprocess.run(
                [_OSASCRIPT, "-e", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.info("macOS Calendar AppleScript failed: %s", exc)
            return []

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.info("macOS Calendar AppleScript error: %s", error_msg)
            if "not allowed" in error_msg.lower() or "不允许" in error_msg:
                logger.info("macOS Calendar access denied — grant in System Settings → Privacy → Calendars")
            return []

        output = result.stdout.strip()
        if not output:
            return []

        events: list[CalendarEvent] = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            event = self._parse_line(line)
            if event is not None:
                # Python-side filter (only for legacy excluded_calendars path)
                if do_python_filter and event.calendar_name in excluded:
                    continue
                events.append(event)

        return events

    @staticmethod
    def _build_script(
        start_date: datetime,
        end_date: datetime,
        included_calendars: list[str] | None = None,
    ) -> str:
        """Build the AppleScript to fetch calendar events.

        Uses short date format (mm/dd/yyyy) which is locale-independent.
        AppleScript 'date' with short format works across all locale settings.

        Args:
            included_calendars: If provided, only query these calendars,
                skipping others entirely in AppleScript for much better performance.
        """
        start_month = start_date.month
        start_day = start_date.day
        start_year = start_date.year
        start_hour = start_date.hour
        start_minute = start_date.minute

        end_month = end_date.month
        end_day = end_date.day
        end_year = end_date.year
        end_hour = end_date.hour
        end_minute = end_date.minute

        # Build calendar filter: only query included calendars in AppleScript
        if included_calendars:
            # Escape double quotes in calendar names for AppleScript string literals
            escaped_names = [name.replace("\\", "\\\\").replace('"', '\\"') for name in included_calendars]
            cal_names_list = ", ".join(f'"{name}"' for name in escaped_names)
            cal_filter_start = f'''
    set includedCalNames to {{{cal_names_list}}}
    repeat with cal in calendars
        set calName to name of cal
        if includedCalNames contains calName then'''
            cal_filter_end = '''
        end if'''
        else:
            cal_filter_start = '''
    repeat with cal in calendars
        set calName to name of cal'''
            cal_filter_end = ""

        return f'''
tell application "Calendar"
    set output to ""
    set startRange to current date
    set year of startRange to {start_year}
    set month of startRange to {start_month}
    set day of startRange to {start_day}
    set hours of startRange to {start_hour}
    set minutes of startRange to {start_minute}
    set seconds of startRange to 0

    set endRange to current date
    set year of endRange to {end_year}
    set month of endRange to {end_month}
    set day of endRange to {end_day}
    set hours of endRange to {end_hour}
    set minutes of endRange to {end_minute}
    set seconds of endRange to 0
{cal_filter_start}
        set calEvents to (every event of cal whose start date >= startRange and start date <= endRange)
        repeat with ev in calEvents
            try
                set evSummary to summary of ev
                set evStart to start date of ev
                set evEnd to end date of ev
                set evLocation to ""
                try
                    set evLocation to location of ev
                end try
                set evDescription to ""
                try
                    set evDescription to description of ev
                end try
                set evUID to uid of ev
                set evAllDay to allday event of ev
                set output to output & evUID & "||" & evSummary & "||" & evStart & "||" & evEnd & "||" & evLocation & "||" & evDescription & "||" & calName & "||" & evAllDay & linefeed
            end try
        end repeat
{cal_filter_end}
    end repeat
    return output
end tell'''

    @staticmethod
    def _parse_line(line: str) -> CalendarEvent | None:
        """Parse a pipe-delimited event line from AppleScript output."""
        parts = line.split("||")
        if len(parts) < 7:
            return None

        uid = parts[0].strip()
        title = parts[1].strip()
        if not title:
            return None

        start_dt = MacCalendarProvider._parse_applescript_date(parts[2].strip())
        end_dt = MacCalendarProvider._parse_applescript_date(parts[3].strip())
        location = parts[4].strip()
        description = parts[5].strip()
        calendar_name = parts[6].strip()
        is_all_day = len(parts) > 7 and parts[7].strip().lower() == "true"

        return CalendarEvent(
            uid=uid,
            title=title[:255] if title else "",
            start_dt=start_dt,
            end_dt=end_dt,
            location=location,
            description=description,
            organizer="",
            calendar_name=calendar_name,
            is_all_day=is_all_day,
        )

    @staticmethod
    def _parse_applescript_date(date_str: str) -> datetime | None:
        """Parse an AppleScript date string.

        Handles both English and Chinese locale formats:
        - English: "Friday, April 25, 2026 at 7:00:00 AM"
        - Chinese: "2026年4月25日 星期五 上午7:00:00" or "2026年4月25日 星期六 00:00:00"
        """
        if not date_str or date_str == "missing value":
            return None

        # Chinese locale format: "2026年4月25日 星期六 00:00:00" or "2026年4月25日 星期六 上午7:00:00"
        import re

        cn_match = re.match(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+\S+\s+"
            r"(?:(?:上午|下午|AM|PM)\s*)?(\d{1,2}):(\d{2}):(\d{2})",
            date_str,
        )
        if cn_match:
            year, month, day = int(cn_match.group(1)), int(cn_match.group(2)), int(cn_match.group(3))
            hour, minute, second = int(cn_match.group(4)), int(cn_match.group(5)), int(cn_match.group(6))
            # Handle 上午/下午 (AM/PM) — 下午 hours need +12 if < 12
            if "下午" in date_str and hour < 12:
                hour += 12
            elif "上午" in date_str and hour == 12:
                hour = 0
            try:
                naive = datetime(year, month, day, hour, minute, second)
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                pass

        # English locale formats
        formats = [
            "%A, %B %d, %Y at %I:%M:%S %p",
            "%B %d, %Y at %I:%M:%S %p",
            "%A, %B %d, %Y",
            "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                naive = datetime.strptime(date_str, fmt)
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                continue

        logger.info("Could not parse AppleScript date: %s", date_str)
        return None

    @staticmethod
    def get_auth_status() -> int:
        """Return current Calendar authorization status via a quick AppleScript test.

        Returns:
            0 = NotDetermined (never prompted)
            2 = Denied
            3 = Authorized
        """
        try:
            result = subprocess.run(
                [_OSASCRIPT, "-e", 'tell application "Calendar" to return name of calendars'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return 3  # Authorized
            error_msg = result.stderr.strip().lower()
            if "not allowed" in error_msg or "不允许" in error_msg:
                return 2  # Denied
            return 0  # NotDetermined or other error
        except Exception:
            return 0
