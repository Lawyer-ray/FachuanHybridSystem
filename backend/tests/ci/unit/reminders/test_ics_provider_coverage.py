"""Coverage tests for reminders/services/calendar_providers/ics_provider.py.

Covers:
  - IcsFileProvider.fetch_events
  - _parse_vevent
  - _get_str
  - _parse_dt (datetime, date, None, with/without tz)
  - _parse_organizer (None, with CN, MAILTO, plain string)
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reminders.services.calendar_providers.ics_provider import IcsFileProvider


class TestParseDt:
    def test_none_value(self):
        result, is_all_day = IcsFileProvider._parse_dt(None)
        assert result is None
        assert is_all_day is False

    def test_datetime_with_tz(self):
        dt = datetime(2024, 6, 15, 10, 30, tzinfo=UTC)
        mock_val = SimpleNamespace(dt=dt)
        result, is_all_day = IcsFileProvider._parse_dt(mock_val)
        assert result == dt
        assert is_all_day is False

    def test_datetime_without_tz(self):
        dt = datetime(2024, 6, 15, 10, 30)
        mock_val = SimpleNamespace(dt=dt)
        result, is_all_day = IcsFileProvider._parse_dt(mock_val)
        assert result is not None
        assert result.tzinfo is not None
        assert is_all_day is False

    def test_date_object(self):
        d = date(2024, 6, 15)
        mock_val = SimpleNamespace(dt=d)
        result, is_all_day = IcsFileProvider._parse_dt(mock_val)
        assert result is not None
        assert result.hour == 0
        assert is_all_day is True

    def test_plain_datetime_no_dt_attr(self):
        # If the value doesn't have .dt attr
        dt = datetime(2024, 6, 15, 10, 30, tzinfo=UTC)
        result, is_all_day = IcsFileProvider._parse_dt(dt)
        assert result == dt

    def test_unknown_type(self):
        mock_val = SimpleNamespace(dt="not a date")
        result, is_all_day = IcsFileProvider._parse_dt(mock_val)
        assert result is None


class TestParseOrganizer:
    def test_none(self):
        assert IcsFileProvider._parse_organizer(None) == ""

    def test_with_cn(self):
        org = SimpleNamespace(params={"CN": "John Doe"})
        assert IcsFileProvider._parse_organizer(org) == "John Doe"

    def test_mailto(self):
        org = MagicMock()
        org.params = {}
        str(org)  # MagicMock str returns name
        # Override __str__
        type(org).__str__ = lambda self: "MAILTO:user@example.com"
        assert IcsFileProvider._parse_organizer(org) == "user@example.com"

    def test_plain_string(self):
        org = MagicMock()
        org.params = {}
        type(org).__str__ = lambda self: "organizer@example.com"
        assert IcsFileProvider._parse_organizer(org) == "organizer@example.com"

    def test_no_params_attr(self):
        # Object without params -> hasattr returns False -> falls through to str(org)
        class OrgNoParams:
            def __str__(self):
                return "test@example.com"
        org = OrgNoParams()
        assert IcsFileProvider._parse_organizer(org) == "test@example.com"

    def test_params_no_cn(self):
        # Has params but no CN -> falls through to str(org)
        org = MagicMock()
        org.params = {}
        type(org).__str__ = lambda self: "mailto:someone@example.com"
        assert IcsFileProvider._parse_organizer(org) == "mailto:someone@example.com"


class TestGetStr:
    def test_none_value(self):
        vevent = SimpleNamespace(get=lambda key: None)
        assert IcsFileProvider._get_str(vevent, "SUMMARY") == ""

    def test_string_value(self):
        vevent = SimpleNamespace(get=lambda key: "Hello" if key == "SUMMARY" else None)
        assert IcsFileProvider._get_str(vevent, "SUMMARY") == "Hello"

    def test_list_value(self):
        vevent = SimpleNamespace(get=lambda key: ["first", "second"] if key == "SUMMARY" else None)
        assert IcsFileProvider._get_str(vevent, "SUMMARY") == "first"

    def test_empty_list(self):
        vevent = SimpleNamespace(get=lambda key: [] if key == "SUMMARY" else None)
        assert IcsFileProvider._get_str(vevent, "SUMMARY") == ""


class TestFetchEvents:
    def test_invalid_ics_content(self):
        provider = IcsFileProvider()
        result = provider.fetch_events(ics_content=b"not valid ics")
        assert result == []

    def test_valid_ics_with_events(self):
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid-1
SUMMARY:Test Event
DTSTART:20240615T103000Z
DTEND:20240615T113000Z
LOCATION:Conference Room
DESCRIPTION:Test description
END:VEVENT
END:VCALENDAR"""
        provider = IcsFileProvider()
        events = provider.fetch_events(ics_content=ics_content)
        assert len(events) == 1
        assert events[0].title == "Test Event"
        assert events[0].location == "Conference Room"

    def test_event_without_summary_skipped(self):
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:no-summary
DTSTART:20240615T103000Z
END:VEVENT
END:VCALENDAR"""
        provider = IcsFileProvider()
        events = provider.fetch_events(ics_content=ics_content)
        assert len(events) == 0

    def test_empty_calendar(self):
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
END:VCALENDAR"""
        provider = IcsFileProvider()
        events = provider.fetch_events(ics_content=ics_content)
        assert events == []
