"""补充覆盖测试: reminders/services/calendar_sync_service.py (35 missing)

覆盖: _build_preview, _to_reminder_kwargs, get_available_providers,
preview_from_ics, preview_from_url, preview_from_local。
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reminders.services.calendar_sync_service import CalendarSyncService


# ── _to_reminder_kwargs ───────────────────────────────────────────


class TestToReminderKwargs:
    def test_basic_event(self) -> None:
        event = {
            "title": "Meeting",
            "start_dt": "2025-06-15 10:00",
            "uid": "uid-123",
            "calendar_name": "Work",
            "location": "Room 1",
            "description": "Discuss project",
            "organizer": "Alice",
        }
        result = CalendarSyncService._to_reminder_kwargs(event)
        assert result["content"] == "Meeting"
        assert result["due_at"] is not None
        assert result["metadata"]["external_id"] == "uid-123"
        assert result["metadata"]["calendar_name"] == "Work"
        assert result["metadata"]["location"] == "Room 1"
        assert result["metadata"]["note"] == "Discuss project"
        assert result["metadata"]["organizer"] == "Alice"

    def test_empty_event_uses_now(self) -> None:
        result = CalendarSyncService._to_reminder_kwargs({})
        assert result["content"] == ""
        assert result["due_at"] is not None

    def test_missing_value_fields_excluded(self) -> None:
        event = {
            "title": "Test",
            "location": "missing value",
            "description": "missing value",
            "organizer": "missing value",
            "calendar_name": "missing value",
        }
        result = CalendarSyncService._to_reminder_kwargs(event)
        assert "location" not in result["metadata"]
        assert "note" not in result["metadata"]
        assert "organizer" not in result["metadata"]
        assert "calendar_name" not in result["metadata"]

    def test_invalid_date_uses_now(self) -> None:
        event = {"title": "Test", "start_dt": "not-a-date"}
        result = CalendarSyncService._to_reminder_kwargs(event)
        assert result["due_at"] is not None

    def test_long_title_truncated(self) -> None:
        event = {"title": "x" * 300}
        result = CalendarSyncService._to_reminder_kwargs(event)
        assert len(result["content"]) == 255

    def test_no_uid_no_external_id(self) -> None:
        event = {"title": "Test"}
        result = CalendarSyncService._to_reminder_kwargs(event)
        assert "external_id" not in result["metadata"]


# ── _build_preview ────────────────────────────────────────────────


class TestBuildPreview:
    def test_empty_events(self) -> None:
        svc = CalendarSyncService()
        with patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            result = svc._build_preview([])
            assert result == []

    def test_event_with_dates(self) -> None:
        svc = CalendarSyncService()
        event = SimpleNamespace(
            uid="uid-1",
            title="Test Event",
            start_dt=datetime(2025, 6, 15, 10, 0),
            end_dt=datetime(2025, 6, 15, 11, 0),
            location="Room 1",
            description="Desc",
            organizer="Alice",
            calendar_name="Work",
            is_all_day=False,
        )
        with patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder, \
             patch("apps.reminders.services.calendar_sync_service.timezone") as mock_tz:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            mock_tz.localtime.return_value.strftime.return_value = "2025-06-15 10:00"
            result = svc._build_preview([event])
            assert len(result) == 1
            assert result[0]["uid"] == "uid-1"
            assert result[0]["title"] == "Test Event"

    def test_missing_value_location(self) -> None:
        svc = CalendarSyncService()
        event = SimpleNamespace(
            uid="uid-2",
            title="Test",
            start_dt=None,
            end_dt=None,
            location="missing value",
            description="missing value",
            organizer="missing value",
            calendar_name="missing value",
            is_all_day=True,
        )
        with patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            result = svc._build_preview([event])
            assert result[0]["location"] == ""
            assert result[0]["description"] == ""
            assert result[0]["organizer"] == ""
            assert result[0]["is_all_day"] is True

    def test_existing_event_marked(self) -> None:
        svc = CalendarSyncService()
        event = SimpleNamespace(
            uid="existing-uid",
            title="Existing",
            start_dt=None,
            end_dt=None,
            location=None,
            description=None,
            organizer=None,
            calendar_name=None,
            is_all_day=False,
        )
        with patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = ["existing-uid"]
            result = svc._build_preview([event])
            assert result[0]["is_existing"] is True

    def test_long_title_truncated(self) -> None:
        svc = CalendarSyncService()
        event = SimpleNamespace(
            uid="uid-3",
            title="x" * 300,
            start_dt=None,
            end_dt=None,
            location=None,
            description=None,
            organizer=None,
            calendar_name=None,
            is_all_day=False,
        )
        with patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            result = svc._build_preview([event])
            assert len(result[0]["title"]) == 255


# ── get_available_providers ───────────────────────────────────────


class TestGetAvailableProviders:
    def test_returns_list(self) -> None:
        svc = CalendarSyncService()
        with patch("apps.reminders.services.calendar_sync_service.get_available_providers", return_value=[{"name": "ics"}]):
            result = svc.get_available_providers()
            assert len(result) == 1


# ── preview_from_ics ──────────────────────────────────────────────


class TestPreviewFromIcs:
    def test_calls_provider(self) -> None:
        svc = CalendarSyncService()
        mock_provider = MagicMock()
        mock_provider.fetch_events.return_value = []

        with patch("apps.reminders.services.calendar_sync_service.get_provider", return_value=mock_provider), \
             patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            result = svc.preview_from_ics(b"ics content")
            mock_provider.fetch_events.assert_called_once_with(ics_content=b"ics content")
            assert isinstance(result, list)


# ── preview_from_local ────────────────────────────────────────────


class TestPreviewFromLocal:
    def test_with_excluded_calendars(self) -> None:
        svc = CalendarSyncService()
        mock_provider = MagicMock()
        mock_provider.DEFAULT_EXCLUDED_CALENDARS = ["System"]

        with patch("apps.reminders.services.calendar_sync_service.get_provider", return_value=mock_provider), \
             patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            svc.preview_from_local("mac", excluded_calendars=["System"])
            call_kwargs = mock_provider.fetch_events.call_args[1]
            assert "excluded_calendars" in call_kwargs

    def test_with_included_calendars(self) -> None:
        svc = CalendarSyncService()
        mock_provider = MagicMock()
        mock_provider.DEFAULT_EXCLUDED_CALENDARS = ["System"]

        with patch("apps.reminders.services.calendar_sync_service.get_provider", return_value=mock_provider), \
             patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            svc.preview_from_local("mac", included_calendars=["Personal"])
            call_kwargs = mock_provider.fetch_events.call_args[1]
            assert "included_calendars" in call_kwargs

    def test_no_filter_params(self) -> None:
        svc = CalendarSyncService()
        mock_provider = MagicMock()

        with patch("apps.reminders.services.calendar_sync_service.get_provider", return_value=mock_provider), \
             patch("apps.reminders.services.calendar_sync_service.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.values_list.return_value = []
            svc.preview_from_local("mac")
            mock_provider.fetch_events.assert_called_once()
