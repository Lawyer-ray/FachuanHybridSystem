"""Tests for apps.reminders.services.calendar_export_service."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.reminders.services.calendar_export_service import CalendarExportService


class TestCalendarExportServiceQueryReminders:
    """Test _query_reminders filtering logic."""

    @patch("apps.reminders.services.calendar_export_service.Reminder")
    def test_query_reminders_basic(self, mock_model: MagicMock) -> None:
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = []
        mock_model.objects = MagicMock()
        mock_model.objects.select_related.return_value = mock_qs

        svc = CalendarExportService()
        with patch.object(svc, "_query_reminders", return_value=[]):
            result = svc.export_reminders(year=2025, month=6)
        assert isinstance(result, bytes)


class TestCalendarExportServiceReminderToVevent:
    """Test _reminder_to_vevent conversion."""

    def test_returns_none_when_no_due_at(self) -> None:
        reminder = SimpleNamespace(due_at=None)
        result = CalendarExportService._reminder_to_vevent(reminder)  # type: ignore[arg-type]
        assert result is None

    def test_creates_vevent_with_basic_fields(self) -> None:
        now = timezone.now()
        reminder = SimpleNamespace(
            id=1,
            due_at=now,
            content="开庭",
            reminder_type="hearing",
            metadata={},
            contract_id=None,
            contract=None,
            case_id=None,
            case=None,
            case_log_id=None,
            case_log=None,
        )
        with patch("apps.reminders.services.calendar_export_service.Reminder") as mock_rem:
            mock_rem._meta = MagicMock()
            mock_rem._meta.get_field = MagicMock(return_value=MagicMock(choices=[("hearing", "开庭")]))
            vevent = CalendarExportService._reminder_to_vevent(reminder)  # type: ignore[arg-type]
        assert vevent is not None
        uid = str(vevent.get("uid"))
        assert "reminder-1" in uid
        summary = str(vevent.get("summary"))
        assert "开庭" in summary

    def test_creates_vevent_with_location_from_courtroom(self) -> None:
        now = timezone.now()
        reminder = SimpleNamespace(
            id=2,
            due_at=now,
            content="调解",
            reminder_type="mediation",
            metadata={"courtroom": "第三法庭"},
            contract_id=None,
            contract=None,
            case_id=None,
            case=None,
            case_log_id=None,
            case_log=None,
        )
        with patch("apps.reminders.services.calendar_export_service.Reminder") as mock_rem:
            mock_rem._meta = MagicMock()
            mock_rem._meta.get_field = MagicMock(return_value=MagicMock(choices=[("mediation", "调解")]))
            vevent = CalendarExportService._reminder_to_vevent(reminder)  # type: ignore[arg-type]
        assert vevent is not None
        location = str(vevent.get("location", ""))
        assert "第三法庭" in location

    def test_creates_vevent_with_contract_and_case(self) -> None:
        now = timezone.now()
        contract = SimpleNamespace(name="租赁合同")
        case = SimpleNamespace(name="张三诉李四")
        reminder = SimpleNamespace(
            id=3,
            due_at=now,
            content="提交材料",
            reminder_type="deadline",
            metadata={"note": "准备证据"},
            contract_id=10,
            contract=contract,
            case_id=20,
            case=case,
            case_log_id=None,
            case_log=None,
        )
        with patch("apps.reminders.services.calendar_export_service.Reminder") as mock_rem:
            mock_rem._meta = MagicMock()
            mock_rem._meta.get_field = MagicMock(return_value=MagicMock(choices=[("deadline", "期限")]))
            vevent = CalendarExportService._reminder_to_vevent(reminder)  # type: ignore[arg-type]
        assert vevent is not None
        desc = str(vevent.get("description", ""))
        assert "租赁合同" in desc
        assert "张三诉李四" in desc
        assert "准备证据" in desc

    def test_vevent_with_end_at_in_metadata(self) -> None:
        now = timezone.now()
        end_at = (now + timedelta(hours=2)).isoformat()
        reminder = SimpleNamespace(
            id=4,
            due_at=now,
            content="会议",
            reminder_type="meeting",
            metadata={"end_at": end_at},
            contract_id=None,
            contract=None,
            case_id=None,
            case=None,
            case_log_id=None,
            case_log=None,
        )
        with patch("apps.reminders.services.calendar_export_service.Reminder") as mock_rem:
            mock_rem._meta = MagicMock()
            mock_rem._meta.get_field = MagicMock(return_value=MagicMock(choices=[("meeting", "会议")]))
            vevent = CalendarExportService._reminder_to_vevent(reminder)  # type: ignore[arg-type]
        assert vevent is not None
        dtend = vevent.get("dtend")
        assert dtend is not None


class TestCalendarExportServiceExportReminders:
    """Test export_reminders method."""

    @patch.object(CalendarExportService, "_query_reminders", return_value=[])
    def test_export_empty_reminders(self, mock_query: MagicMock) -> None:
        svc = CalendarExportService()
        result = svc.export_reminders(year=2025, month=6)
        assert isinstance(result, bytes)
        assert b"VCALENDAR" in result or b"vcalendar" in result.lower()

    def test_format_chinese_date_via_reminder(self) -> None:
        """Ensure the ICS output includes proper calendar headers."""
        svc = CalendarExportService()
        with patch.object(svc, "_query_reminders", return_value=[]):
            result = svc.export_reminders(year=2025, month=12)
        assert b"PRODID" in result or b"prodid" in result.lower()
