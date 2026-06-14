"""reminders/services/calendar_providers/windows_provider.py 单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reminders.services.calendar_providers.base import CalendarEvent


class TestWindowsOutlookProviderFetchEvents:
    def test_no_win32com_returns_empty(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        with patch.dict("sys.modules", {"win32com.client": None}):
            # ImportError path
            import importlib
            import apps.reminders.services.calendar_providers.windows_provider as mod
            original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__  # type: ignore[union-attr]

            def _mock_import(name: str, *args: object, **kwargs: object) -> MagicMock:
                if name == "win32com.client":
                    raise ImportError("no win32com")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_mock_import):
                result = provider.fetch_events()
                assert result == []

    def test_outlook_dispatch_failure(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        mock_win32 = MagicMock()
        mock_win32.Dispatch.side_effect = Exception("COM error")
        with patch.dict("sys.modules", {"win32com.client": mock_win32}):
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: mock_win32 if "win32com" in name else MagicMock()):
                result = provider.fetch_events()
                assert result == []

    def test_empty_calendar(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        mock_outlook = MagicMock()
        mock_namespace = MagicMock()
        mock_calendar = MagicMock()
        mock_items = MagicMock()
        mock_items.__iter__ = MagicMock(return_value=iter([]))
        mock_calendar.Items = mock_items
        mock_namespace.GetDefaultFolder.return_value = mock_calendar
        mock_outlook.GetNamespace.return_value = mock_namespace

        mock_win32 = MagicMock()
        mock_win32.Dispatch.return_value = mock_outlook
        with patch.dict("sys.modules", {"win32com.client": mock_win32}):
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: mock_win32 if "win32com" in name else MagicMock()):
                result = provider.fetch_events()
                assert result == []


class TestConvertEvent:
    def test_valid_item(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        item = SimpleNamespace(
            Subject="Meeting",
            Start=datetime(2026, 1, 1, 10, 0),
            End=datetime(2026, 1, 1, 11, 0),
            EntryID="uid123",
            Location="Room 1",
            Body="Notes",
            Organizer="Boss",
            AllDayEvent=False,
        )
        event = provider._convert_event(item)
        assert event is not None
        assert event.title == "Meeting"
        assert event.uid == "uid123"
        assert event.location == "Room 1"
        assert event.description == "Notes"
        assert event.organizer == "Boss"
        assert event.is_all_day is False

    def test_empty_title_returns_none(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()
        item = SimpleNamespace(Subject="")
        assert provider._convert_event(item) is None

    def test_pywintypes_datetime_conversion(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()

        class FakeWinTime:
            year = 2026
            month = 6
            day = 15
            hour = 14
            minute = 30
            second = 0

        item = SimpleNamespace(
            Subject="Event",
            Start=FakeWinTime(),
            End=FakeWinTime(),
            EntryID="id",
            Location="",
            Body="",
            Organizer="",
            AllDayEvent=True,
        )
        event = provider._convert_event(item)
        assert event is not None
        assert event.start_dt is not None
        assert event.start_dt.year == 2026

    def test_invalid_pywintypes(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()

        class BadTime:
            def __getattr__(self, name: str) -> int:
                raise TypeError("no attr")

        item = SimpleNamespace(
            Subject="Event",
            Start=BadTime(),
            End=BadTime(),
            EntryID="id",
            Location="",
            Body="",
            Organizer="",
            AllDayEvent=False,
        )
        event = provider._convert_event(item)
        assert event is not None
        assert event.start_dt is None
        assert event.end_dt is None

    def test_conversion_exception(self) -> None:
        from apps.reminders.services.calendar_providers.windows_provider import WindowsOutlookProvider

        provider = WindowsOutlookProvider()

        class BadItem:
            Subject = "E"

            def __getattr__(self, name: str) -> None:
                raise Exception("fail")

        result = provider._convert_event(BadItem())
        assert result is None
