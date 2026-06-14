"""Unit tests for reminders.admin.reminder_admin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.reminders.admin.reminder_admin import ReminderAdminForm


class TestReminderAdminForm:
    """测试 ReminderAdminForm 的 clean_metadata 方法"""

    def test_clean_metadata_none(self) -> None:
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": None}
        assert form.clean_metadata() == {}

    def test_clean_metadata_empty_string(self) -> None:
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": ""}
        assert form.clean_metadata() == {}

    def test_clean_metadata_valid_dict(self) -> None:
        form = ReminderAdminForm()
        data = {"source": "test"}
        form.cleaned_data = {"metadata": data}
        assert form.clean_metadata() == data

    def test_clean_metadata_valid_json_string(self) -> None:
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": '{"source": "test"}'}
        result = form.clean_metadata()
        assert result == {"source": "test"}

    def test_clean_metadata_invalid_json(self) -> None:
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": "not json"}
        with pytest.raises(Exception):
            form.clean_metadata()

    def test_clean_metadata_array_json(self) -> None:
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": "[1, 2, 3]"}
        with pytest.raises(Exception):
            form.clean_metadata()


class TestReminderAdminCalendarHelpers:
    """测试 ReminderAdmin 的日历辅助方法"""

    def _make_admin(self):
        from apps.reminders.admin.reminder_admin import ReminderAdmin
        from apps.reminders.models import Reminder

        admin = ReminderAdmin(Reminder, MagicMock())
        return admin

    def test_parse_year_month_defaults(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {}
        year, month = admin._parse_year_month(request)
        assert isinstance(year, int)
        assert isinstance(month, int)
        assert 1 <= month <= 12

    def test_parse_year_month_valid(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {"year": "2025", "month": "6"}
        year, month = admin._parse_year_month(request)
        assert year == 2025
        assert month == 6

    def test_parse_year_month_invalid_year(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {"year": "abc", "month": "6"}
        from django.utils import timezone
        year, month = admin._parse_year_month(request)
        assert year == timezone.localdate().year

    def test_parse_year_month_invalid_month(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {"year": "2025", "month": "13"}
        from django.utils import timezone
        year, month = admin._parse_year_month(request)
        assert month == timezone.localdate().month

    def test_parse_year_month_out_of_range_year(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {"year": "1969", "month": "6"}
        from django.utils import timezone
        year, _ = admin._parse_year_month(request)
        assert year == timezone.localdate().year

    def test_shift_month_forward(self) -> None:
        admin = self._make_admin()
        year, month = admin._shift_month(2025, 12, 1)
        assert year == 2026
        assert month == 1

    def test_shift_month_backward(self) -> None:
        admin = self._make_admin()
        year, month = admin._shift_month(2025, 1, -1)
        assert year == 2024
        assert month == 12

    def test_parse_positive_int_none(self) -> None:
        admin = self._make_admin()
        assert admin._parse_positive_int("") is None
        assert admin._parse_positive_int("  ") is None

    def test_parse_positive_int_valid(self) -> None:
        admin = self._make_admin()
        assert admin._parse_positive_int("42") == 42

    def test_parse_positive_int_negative(self) -> None:
        admin = self._make_admin()
        assert admin._parse_positive_int("-5") is None

    def test_parse_positive_int_invalid(self) -> None:
        admin = self._make_admin()
        assert admin._parse_positive_int("abc") is None

    def test_build_calendar_url(self) -> None:
        admin = self._make_admin()
        url = admin._build_calendar_url(2025, 6, {"reminder_type": "hearing"})
        assert "year=2025" in url
        assert "month=6" in url
        assert "reminder_type=hearing" in url

    def test_build_calendar_weeks(self) -> None:
        admin = self._make_admin()
        weeks = admin._build_calendar_weeks(year=2025, month=6, events_by_day={})
        assert len(weeks) >= 4  # At least 4 weeks
        for week in weeks:
            assert len(week) == 7  # 7 days per week

    def test_safe_return_url_valid(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.POST = {"return_url": "/admin/safe/"}
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        url = admin._safe_return_url(request=request)
        assert url == "/admin/safe/"

    def test_safe_return_url_unsafe_fallback(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.POST = {"return_url": "http://evil.com/hack"}
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        url = admin._safe_return_url(request=request)
        assert "evil" not in url
