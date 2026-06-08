"""Coverage tests for reminders.services.calendar_providers and calendar_export_service."""

from unittest.mock import MagicMock, patch

import pytest


class TestIcsFileProvider:
    def test_fetch_events_invalid_content(self):
        from apps.reminders.services.calendar_providers.ics_provider import IcsFileProvider

        provider = IcsFileProvider()
        result = provider.fetch_events(ics_content=b"invalid ics content")
        assert result == []

    def test_fetch_events_empty(self):
        from apps.reminders.services.calendar_providers.ics_provider import IcsFileProvider

        provider = IcsFileProvider()
        ics = b"""BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:test\nEND:VCALENDAR"""
        result = provider.fetch_events(ics_content=ics)
        assert isinstance(result, list)

    def test_parse_vevent_no_summary(self):
        from apps.reminders.services.calendar_providers.ics_provider import IcsFileProvider

        provider = IcsFileProvider()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.return_value = None
        mock_component.__getitem__ = MagicMock(side_effect=KeyError)
        result = provider._parse_vevent(mock_component)
        assert result is None

    def test_get_str(self):
        from apps.reminders.services.calendar_providers.ics_provider import IcsFileProvider

        provider = IcsFileProvider()
        mock_comp = MagicMock()
        mock_val = MagicMock()
        mock_val.__str__ = MagicMock(return_value="test")
        mock_comp.get.return_value = mock_val
        result = provider._get_str(mock_comp, "SUMMARY")
        assert result == "test"


class TestWindowsOutlookProvider:
    def test_fetch_events_no_win32(self):
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}):
            result = provider.fetch_events()
            assert result == []


class TestCalendarExportService:
    def test_export_reminders_empty(self):
        from apps.reminders.services.calendar_export_service import CalendarExportService

        svc = CalendarExportService()
        with patch.object(svc, "_query_reminders", return_value=[]):
            result = svc.export_reminders(year=2024, month=1)
            assert isinstance(result, bytes)
            assert b"VCALENDAR" in result
