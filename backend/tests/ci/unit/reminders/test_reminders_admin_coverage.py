"""Reminders Admin 测试 - 增强覆盖 ReminderAdmin 未覆盖代码路径"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.reminders.admin.reminder_admin import ReminderAdmin, ReminderAdminForm
from apps.reminders.models import Reminder, ReminderType

User = get_user_model()


def _make_admin():
    return ReminderAdmin(Reminder, AdminSite())


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestReminderAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "id" in admin.list_display
        assert "due_at" in admin.list_display
        assert "reminder_type" in admin.list_display
        assert "content" in admin.list_display
        assert "contract" in admin.list_display
        assert "case" in admin.list_display
        assert "case_log" in admin.list_display

    def test_list_display_links(self):
        admin = _make_admin()
        assert "id" in admin.list_display_links
        assert "content" in admin.list_display_links

    def test_list_filter(self):
        admin = _make_admin()
        assert "reminder_type" in admin.list_filter
        assert "created_at" in admin.list_filter

    def test_search_fields(self):
        admin = _make_admin()
        assert "content" in admin.search_fields

    def test_readonly_fields(self):
        admin = _make_admin()
        assert "metadata_display" in admin.readonly_fields
        assert "created_at" in admin.readonly_fields
        assert "updated_at" in admin.readonly_fields

    def test_ordering(self):
        admin = _make_admin()
        assert "-due_at" in admin.ordering

    def test_date_hierarchy(self):
        admin = _make_admin()
        assert admin.date_hierarchy == "due_at"

    def test_list_per_page(self):
        admin = _make_admin()
        assert admin.list_per_page == 30

    def test_change_list_template(self):
        admin = _make_admin()
        assert "change_list" in admin.change_list_template

    def test_autocomplete_fields(self):
        admin = _make_admin()
        assert "contract" in admin.autocomplete_fields
        assert "case" in admin.autocomplete_fields
        assert "case_log" in admin.autocomplete_fields


@pytest.mark.django_db
class TestReminderAdminMetadataDisplay:
    """测试 metadata_display 渲染"""

    def test_empty_dict(self):
        admin = _make_admin()
        obj = MagicMock(metadata={})
        assert admin.metadata_display(obj) == "—"

    def test_none(self):
        admin = _make_admin()
        obj = MagicMock(metadata=None)
        assert admin.metadata_display(obj) == "—"

    def test_non_dict(self):
        admin = _make_admin()
        obj = MagicMock(metadata="not a dict")
        assert admin.metadata_display(obj) == "—"

    def test_with_data(self):
        admin = _make_admin()
        obj = MagicMock(metadata={"source": "court_sms", "file_name": "test.pdf"})
        result = str(admin.metadata_display(obj))
        assert "court_sms" in result
        assert "test.pdf" in result
        assert "<table" in result

    def test_with_empty_string_values(self):
        admin = _make_admin()
        obj = MagicMock(metadata={"key1": "", "key2": "value"})
        result = str(admin.metadata_display(obj))
        assert "key1" in result
        assert "key2" in result


@pytest.mark.django_db
class TestReminderAdminCalendarHelpers:
    """测试 Calendar 辅助方法"""

    def test_shift_month_forward(self):
        admin = _make_admin()
        year, month = admin._shift_month(2025, 12, 1)
        assert year == 2026
        assert month == 1

    def test_shift_month_backward(self):
        admin = _make_admin()
        year, month = admin._shift_month(2025, 1, -1)
        assert year == 2024
        assert month == 12

    def test_shift_month_same_year(self):
        admin = _make_admin()
        year, month = admin._shift_month(2025, 6, 3)
        assert year == 2025
        assert month == 9

    def test_parse_positive_int_valid(self):
        admin = _make_admin()
        assert admin._parse_positive_int("5") == 5
        assert admin._parse_positive_int("0") is None
        assert admin._parse_positive_int("-1") is None

    def test_parse_positive_int_empty(self):
        admin = _make_admin()
        assert admin._parse_positive_int("") is None
        assert admin._parse_positive_int("   ") is None

    def test_parse_positive_int_invalid(self):
        admin = _make_admin()
        assert admin._parse_positive_int("abc") is None

    def test_parse_year_month_valid(self):
        admin = _make_admin()
        request = _make_request(data={"year": "2025", "month": "6"})
        year, month = admin._parse_year_month(request)
        assert year == 2025
        assert month == 6

    def test_parse_year_month_missing(self):
        admin = _make_admin()
        request = _make_request()
        year, month = admin._parse_year_month(request)
        today = timezone.localdate()
        assert year == today.year

    def test_parse_year_month_invalid(self):
        admin = _make_admin()
        request = _make_request(data={"year": "abc", "month": "xyz"})
        year, month = admin._parse_year_month(request)
        today = timezone.localdate()
        assert year == today.year
        assert month == today.month

    def test_parse_year_month_out_of_range(self):
        admin = _make_admin()
        request = _make_request(data={"year": "2025", "month": "13"})
        year, month = admin._parse_year_month(request)
        today = timezone.localdate()
        assert month == today.month

    def test_parse_year_month_year_out_of_range(self):
        admin = _make_admin()
        request = _make_request(data={"year": "1969", "month": "6"})
        year, month = admin._parse_year_month(request)
        today = timezone.localdate()
        assert year == today.year

    def test_build_calendar_weeks(self):
        admin = _make_admin()
        weeks = admin._build_calendar_weeks(year=2025, month=6, events_by_day={1: []})
        assert isinstance(weeks, list)
        assert len(weeks) >= 4
        for week in weeks:
            assert len(week) == 7

    def test_build_calendar_url(self):
        admin = _make_admin()
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            url = admin._build_calendar_url(2025, 6, {"status": "overdue"})
            assert "2025" in url
            assert "overdue" in url

    def test_build_calendar_url_empty_filters(self):
        admin = _make_admin()
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            url = admin._build_calendar_url(2025, 6, {})
            assert isinstance(url, str)


@pytest.mark.django_db
class TestReminderAdminSafeReturnUrl:
    """测试 _safe_return_url"""

    def test_valid_url(self):
        admin = _make_admin()
        request = MagicMock()
        request.POST = {"return_url": "/admin/some-page/"}
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        url = admin._safe_return_url(request=request)
        assert url == "/admin/some-page/"

    def test_empty_url(self):
        admin = _make_admin()
        request = MagicMock()
        request.POST = {}
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        url = admin._safe_return_url(request=request)
        assert "calendar" in url

    def test_unsafe_url(self):
        admin = _make_admin()
        request = MagicMock()
        request.POST = {"return_url": "http://evil.com/hack"}
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        url = admin._safe_return_url(request=request)
        assert "calendar" in url


@pytest.mark.django_db
class TestReminderAdminCalendarViewMethods:
    """测试 Calendar 视图方法"""

    def test_calendar_create_view_not_post(self):
        admin = _make_admin()
        request = MagicMock()
        request.method = "GET"
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        request.method = "POST"
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_empty_content(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "",
            "reminder_type": "general",
            "due_date": "2025-06-01",
            "due_time": "10:00",
            "target_type": "",
            "target_id": "",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_invalid_type(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "INVALID_TYPE",
            "due_date": "2025-06-01",
            "due_time": "10:00",
            "target_type": "",
            "target_id": "",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_missing_date(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "general",
            "due_date": "",
            "due_time": "10:00",
            "target_type": "",
            "target_id": "",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_invalid_target_type(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "general",
            "due_date": "2025-06-01",
            "due_time": "10:00",
            "target_type": "invalid",
            "target_id": "1",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_target_id_without_type(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "general",
            "due_date": "2025-06-01",
            "due_time": "10:00",
            "target_type": "",
            "target_id": "5",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_type_without_id(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "general",
            "due_date": "2025-06-01",
            "due_time": "10:00",
            "target_type": "contract",
            "target_id": "",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_create_view_invalid_datetime(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.POST = {
            "content": "test",
            "reminder_type": "general",
            "due_date": "not-a-date",
            "due_time": "not-a-time",
            "target_type": "",
            "target_id": "",
            "return_url": "/admin/calendar/",
        }
        request.get_host.return_value = "localhost"
        request.is_secure.return_value = False
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/calendar/"):
            result = admin.calendar_create_view(request)
            assert result.status_code == 302

    def test_calendar_target_options_view_not_get(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        result = admin.calendar_target_options_view(request)
        assert result.status_code == 405

    def test_calendar_target_options_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        request.method = "GET"
        result = admin.calendar_target_options_view(request)
        assert result.status_code == 403

    def test_calendar_sync_providers_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_sync_providers_view(request)
        assert result.status_code == 403

    def test_calendar_sync_preview_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 403

    def test_calendar_sync_preview_view_invalid_source(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"source": "invalid"}
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 400

    def test_calendar_sync_preview_view_ics_no_file(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"source": "ics_file"}
        request.FILES = {}
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 400

    def test_calendar_sync_preview_view_ics_wrong_ext(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"source": "ics_file"}
        mock_file = MagicMock()
        mock_file.name = "test.txt"
        mock_file.size = 100
        request.FILES = {"ics_file": mock_file}
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 400

    def test_calendar_sync_preview_view_ics_too_large(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"source": "ics_file"}
        mock_file = MagicMock()
        mock_file.name = "test.ics"
        mock_file.size = 10 * 1024 * 1024  # 10MB
        request.FILES = {"ics_file": mock_file}
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 400

    def test_calendar_sync_preview_view_url_empty(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"source": "ics_url", "url": ""}
        result = admin.calendar_sync_preview_view(request)
        assert result.status_code == 400

    def test_calendar_sync_import_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_sync_import_view(request)
        assert result.status_code == 403

    def test_calendar_sync_import_view_invalid_json(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"events": "not-json"}
        result = admin.calendar_sync_import_view(request)
        assert result.status_code == 400

    def test_calendar_sync_import_view_not_list(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.POST = {"events": '{"key": "value"}'}
        result = admin.calendar_sync_import_view(request)
        assert result.status_code == 400

    def test_calendar_sync_open_privacy_non_darwin(self):
        admin = _make_admin()
        request = MagicMock()
        with patch("platform.system", return_value="Linux"):
            result = admin.calendar_sync_open_privacy_view(request)
            assert result.status_code == 200
            data = json.loads(result.content)
            assert data["ok"] is False

    def test_calendar_sync_calendars_view_no_permission(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_sync_calendars_view(request)
        assert result.status_code == 403

    def test_calendar_sync_calendars_view_invalid_provider(self):
        admin = _make_admin()
        admin.has_add_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.GET = {"provider": "invalid"}
        result = admin.calendar_sync_calendars_view(request)
        assert result.status_code == 400

    def test_calendar_sync_clear_view_no_permission(self):
        admin = _make_admin()
        admin.has_delete_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_sync_clear_view(request)
        assert result.status_code == 403

    def test_calendar_export_view_no_permission(self):
        admin = _make_admin()
        admin.has_view_permission = MagicMock(return_value=False)
        request = MagicMock()
        result = admin.calendar_export_view(request)
        assert result.status_code == 403

    def test_group_events_by_day_unbound(self):
        admin = _make_admin()
        now = timezone.now()
        reminder = MagicMock()
        reminder.id = 1
        reminder.due_at = now
        reminder.contract_id = None
        reminder.case_id = None
        reminder.case_log_id = None
        reminder.reminder_type = "general"
        reminder.content = "test content"
        reminder.metadata = {}
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/change/1/"):
            events = admin._group_events_by_day(reminders=[reminder])
            assert isinstance(events, dict)
            day = timezone.localtime(now).day
            assert day in events
            assert len(events[day]) == 1
            assert events[day][0]["target_type"] == "未绑定"

    def test_group_events_by_day_with_contract(self):
        admin = _make_admin()
        now = timezone.now()
        reminder = MagicMock()
        reminder.id = 2
        reminder.due_at = now
        reminder.contract_id = 1
        reminder.contract = MagicMock()
        reminder.contract.name = "测试合同"
        reminder.case_id = None
        reminder.case = None
        reminder.case_log_id = None
        reminder.case_log = None
        reminder.reminder_type = "payment_deadline"
        reminder.content = "付款提醒"
        reminder.metadata = {"courtroom": "第三法庭", "lawyer_name": "张三"}
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/change/2/"):
            events = admin._group_events_by_day(reminders=[reminder])
            day = timezone.localtime(now).day
            assert events[day][0]["target_type"] == "合同"
            assert events[day][0]["courtroom"] == "第三法庭"

    def test_group_events_by_day_with_case(self):
        admin = _make_admin()
        now = timezone.now()
        reminder = MagicMock()
        reminder.id = 3
        reminder.due_at = now
        reminder.contract_id = None
        reminder.contract = None
        reminder.case_id = 1
        reminder.case = MagicMock()
        reminder.case.name = "测试案件"
        reminder.case_log_id = None
        reminder.case_log = None
        reminder.reminder_type = "hearing"
        reminder.content = "开庭提醒"
        reminder.metadata = {}
        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/change/3/"):
            events = admin._group_events_by_day(reminders=[reminder])
            day = timezone.localtime(now).day
            assert events[day][0]["target_type"] == "案件"

    def test_group_events_by_day_hearing_merge(self):
        admin = _make_admin()
        now = timezone.now()
        r1 = MagicMock()
        r1.id = 1
        r1.due_at = now
        r1.contract_id = None
        r1.contract = None
        r1.case_id = 1
        r1.case = MagicMock()
        r1.case.name = "案件"
        r1.case_log_id = None
        r1.case_log = None
        r1.reminder_type = "hearing"
        r1.content = "庭审"
        r1.metadata = {"source_id": "S001", "lawyer_name": "张三"}

        r2 = MagicMock()
        r2.id = 2
        r2.due_at = now
        r2.contract_id = None
        r2.contract = None
        r2.case_id = 1
        r2.case = MagicMock()
        r2.case.name = "案件"
        r2.case_log_id = None
        r2.case_log = None
        r2.reminder_type = "hearing"
        r2.content = "庭审"
        r2.metadata = {"source_id": "S001", "lawyer_name": "李四"}

        with patch("apps.reminders.admin.reminder_admin.reverse", return_value="/admin/change/1/"):
            events = admin._group_events_by_day(reminders=[r1, r2])
            day = timezone.localtime(now).day
            # Should merge into 1 event with aggregated lawyers
            assert len(events[day]) == 1
            assert "张三" in events[day][0]["lawyer_name"]
            assert "李四" in events[day][0]["lawyer_name"]

    def test_query_month_reminders_filters(self):
        admin = _make_admin()
        from datetime import date as date_type

        # Test with scope and status filters
        reminders = admin._query_month_reminders(
            month_start=date_type(2025, 6, 1),
            next_month_start=date_type(2025, 7, 1),
            selected_type="",
            selected_scope="contract",
            selected_status="overdue",
        )
        assert isinstance(reminders, list)

    def test_query_month_reminders_with_type_filter(self):
        admin = _make_admin()
        from datetime import date as date_type

        reminders = admin._query_month_reminders(
            month_start=date_type(2025, 6, 1),
            next_month_start=date_type(2025, 7, 1),
            selected_type="hearing",
            selected_scope="all",
            selected_status="all",
        )
        assert isinstance(reminders, list)


@pytest.mark.django_db
class TestReminderAdminFormExtended:
    """测试 ReminderAdminForm"""

    def test_clean_metadata_none(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": None}
        result = form.clean_metadata()
        assert result == {}

    def test_clean_metadata_empty_string(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": ""}
        result = form.clean_metadata()
        assert result == {}

    def test_clean_metadata_valid_dict(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": {"key": "value"}}
        result = form.clean_metadata()
        assert result == {"key": "value"}

    def test_clean_metadata_valid_json_string(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": '{"source": "manual"}'}
        result = form.clean_metadata()
        assert result == {"source": "manual"}

    def test_clean_metadata_invalid_json(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": "not-json"}
        with pytest.raises(Exception):
            form.clean_metadata()

    def test_clean_metadata_json_array(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": '[1, 2, 3]'}
        with pytest.raises(Exception):
            form.clean_metadata()

    def test_clean_metadata_int_type(self):
        form = ReminderAdminForm()
        form.cleaned_data = {"metadata": 42}
        with pytest.raises(Exception):
            form.clean_metadata()
