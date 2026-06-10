"""Tests for reminders services."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from django.utils import timezone


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------

class TestValidatorsNormalizeTargetId:
    def test_none_returns_none(self):
        from apps.reminders.services.validators import normalize_target_id
        assert normalize_target_id(None, field_name="x") is None

    def test_positive_int(self):
        from apps.reminders.services.validators import normalize_target_id
        assert normalize_target_id(5, field_name="x") == 5

    def test_zero_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_target_id
        with pytest.raises(ValidationException):
            normalize_target_id(0, field_name="x")

    def test_negative_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_target_id
        with pytest.raises(ValidationException):
            normalize_target_id(-1, field_name="x")

    def test_bool_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_target_id
        with pytest.raises(ValidationException):
            normalize_target_id(True, field_name="x")


class TestValidatorsValidatePositiveId:
    def test_valid(self):
        from apps.reminders.services.validators import validate_positive_id
        validate_positive_id(1, field_name="x")

    def test_bool_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import validate_positive_id
        with pytest.raises(ValidationException):
            validate_positive_id(True, field_name="x")


class TestValidatorsBindingExclusive:
    def test_no_binding_ok(self):
        from apps.reminders.services.validators import validate_binding_exclusive
        validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)

    def test_single_binding_ok(self):
        from apps.reminders.services.validators import validate_binding_exclusive
        validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)

    def test_multiple_bindings_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import validate_binding_exclusive
        with pytest.raises(ValidationException):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)


class TestValidatorsFkExists:
    def test_none_skips(self):
        from apps.reminders.services.validators import validate_fk_exists
        validate_fk_exists(contract_id=None, case_id=None, case_log_id=None)

    def test_contract_not_found_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import validate_fk_exists
        mock_query = MagicMock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException):
            validate_fk_exists(contract_id=999, case_id=None, case_log_id=None, contract_target_query=mock_query)

    def test_contract_found_ok(self):
        from apps.reminders.services.validators import validate_fk_exists
        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=1, case_id=None, case_log_id=None, contract_target_query=mock_query)


class TestValidatorsNormalizeReminderType:
    def test_valid_type(self):
        from apps.reminders.services.validators import normalize_reminder_type
        assert normalize_reminder_type("hearing") == "hearing"

    def test_empty_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_reminder_type
        with pytest.raises(ValidationException):
            normalize_reminder_type("")

    def test_invalid_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_reminder_type
        with pytest.raises(ValidationException):
            normalize_reminder_type("nonexistent_type")


class TestValidatorsNormalizeContent:
    def test_valid(self):
        from apps.reminders.services.validators import normalize_content
        assert normalize_content("  test content  ") == "test content"

    def test_empty_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_content
        with pytest.raises(ValidationException):
            normalize_content("")

    def test_too_long_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_content
        with pytest.raises(ValidationException):
            normalize_content("x" * 300)


class TestValidatorsNormalizeDueAt:
    def test_aware_datetime(self):
        from apps.reminders.services.validators import normalize_due_at
        dt = timezone.now()
        assert normalize_due_at(dt) == dt

    def test_naive_made_aware(self):
        from apps.reminders.services.validators import normalize_due_at
        dt = datetime(2026, 1, 1, 12, 0, 0)
        result = normalize_due_at(dt)
        assert timezone.is_aware(result)


class TestValidatorsNormalizeMetadata:
    def test_none_returns_empty(self):
        from apps.reminders.services.validators import normalize_metadata
        assert normalize_metadata(None) == {}

    def test_valid_dict(self):
        from apps.reminders.services.validators import normalize_metadata
        data = {"key": "value"}
        assert normalize_metadata(data) == data

    def test_non_dict_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_metadata
        with pytest.raises(ValidationException):
            normalize_metadata([1, 2, 3])

    def test_non_serializable_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.reminders.services.validators import normalize_metadata
        with pytest.raises(ValidationException):
            normalize_metadata({"key": timezone.now()})


# ---------------------------------------------------------------------------
# reminder_parser_service
# ---------------------------------------------------------------------------

class TestReminderParserInferType:
    def test_hearing(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type
        assert _infer_reminder_type("开庭通知") == "hearing"

    def test_evidence_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type
        assert _infer_reminder_type("举证期限") == "evidence_deadline"

    def test_appeal_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type
        assert _infer_reminder_type("上诉期限") == "appeal_deadline"

    def test_payment_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type
        assert _infer_reminder_type("缴费期限") == "payment_deadline"

    def test_default_other(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type
        assert _infer_reminder_type("随便什么文字") == "other"


class TestReminderParserParseDate:
    def test_iso_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        result = _parse_date("2026-01-15")
        assert result is not None and result.day == 15

    def test_slash_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        result = _parse_date("2026/01/15")
        assert result is not None

    def test_dot_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        result = _parse_date("2026.01.15")
        assert result is not None

    def test_chinese_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        result = _parse_date("2026年01月15日")
        assert result is not None

    def test_empty(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        assert _parse_date("") is None

    def test_invalid(self):
        from apps.reminders.services.reminder_parser_service import _parse_date
        assert _parse_date("not-a-date") is None


class TestReminderParserExtractTimeNearDate:
    def test_morning(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date
        text = "2026年1月15日上午9点开庭"
        result = _extract_time_near_date(text, 10)
        assert result is not None
        assert result[0] == 9

    def test_afternoon(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date
        text = "2026年1月15日下午3点"
        result = _extract_time_near_date(text, 10)
        assert result is not None
        assert result[0] == 15

    def test_half_hour(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date
        text = "2026年1月15日下午3点半"
        result = _extract_time_near_date(text, 10)
        assert result is not None
        assert result == (15, 30)

    def test_no_time(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date
        text = "2026年1月15日"
        result = _extract_time_near_date(text, 10)
        assert result is None


class TestReminderParserExtractSentence:
    def test_basic(self):
        from apps.reminders.services.reminder_parser_service import _extract_sentence
        text = "第一句。第二句开庭通知第三句。"
        result = _extract_sentence(text, 6, 10)
        assert "开庭" in result


class TestReminderParserParseRemindersFromText:
    def test_empty_text(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text
        assert parse_reminders_from_text("") == []
        assert parse_reminders_from_text(None) == []

    def test_single_date_hearing(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text
        text = "定于2026年1月15日上午9点开庭。"
        results = parse_reminders_from_text(text)
        assert len(results) >= 1
        assert results[0].reminder_type == "hearing"

    def test_no_dates(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text
        results = parse_reminders_from_text("没有日期的文本")
        assert results == []

    def test_dedup(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text
        text = "2026年1月15日开庭 2026年1月15日举证"
        results = parse_reminders_from_text(text)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# reminder_service
# ---------------------------------------------------------------------------

class TestReminderServiceList:
    @pytest.mark.django_db
    def test_list_empty(self):
        from apps.reminders.services.reminder_service import ReminderService
        svc = ReminderService(
            contract_target_query=MagicMock(),
            case_target_query=MagicMock(),
            case_log_target_query=MagicMock(),
        )
        qs = svc.list_reminders()
        assert list(qs) == []

    @pytest.mark.django_db
    def test_multiple_filters_raises(self):
        from apps.reminders.services.reminder_service import ReminderService
        from apps.core.exceptions import ValidationException
        svc = ReminderService(
            contract_target_query=MagicMock(),
            case_target_query=MagicMock(),
            case_log_target_query=MagicMock(),
        )
        with pytest.raises(ValidationException):
            svc.list_reminders(contract_id=1, case_id=2)


class TestReminderServiceGetReminder:
    @pytest.mark.django_db
    def test_not_found_raises(self):
        from apps.reminders.services.reminder_service import ReminderService
        from apps.core.exceptions import NotFoundError
        svc = ReminderService(
            contract_target_query=MagicMock(),
            case_target_query=MagicMock(),
            case_log_target_query=MagicMock(),
        )
        with pytest.raises(NotFoundError):
            svc.get_reminder(999999)


# ---------------------------------------------------------------------------
# calendar_sync_service
# ---------------------------------------------------------------------------

class TestCalendarSyncServiceToReminderKwargs:
    def test_basic_conversion(self):
        from apps.reminders.services.calendar_sync_service import CalendarSyncService
        event = {"title": "开庭", "start_dt": "2026-01-15 09:00", "uid": "evt123"}
        kwargs = CalendarSyncService._to_reminder_kwargs(event)
        assert kwargs["content"] == "开庭"
        assert kwargs["reminder_type"] == "other"
        assert kwargs["metadata"]["external_id"] == "evt123"

    def test_missing_start_dt(self):
        from apps.reminders.services.calendar_sync_service import CalendarSyncService
        event = {"title": "会议", "start_dt": ""}
        kwargs = CalendarSyncService._to_reminder_kwargs(event)
        assert kwargs["due_at"] is not None

    def test_missing_value_filter(self):
        from apps.reminders.services.calendar_sync_service import CalendarSyncService
        event = {"title": "T", "start_dt": "2026-01-15 09:00", "location": "missing value"}
        kwargs = CalendarSyncService._to_reminder_kwargs(event)
        assert "location" not in kwargs["metadata"]


class TestCalendarSyncServiceBuildPreview:
    @pytest.mark.django_db
    def test_empty_events(self):
        from apps.reminders.services.calendar_sync_service import CalendarSyncService
        svc = CalendarSyncService()
        assert svc._build_preview([]) == []


# ---------------------------------------------------------------------------
# calendar_export_service
# ---------------------------------------------------------------------------

class TestCalendarExportServiceReminderToVevent:
    def test_no_due_at_returns_none(self):
        from apps.reminders.services.calendar_export_service import CalendarExportService
        reminder = MagicMock()
        reminder.due_at = None
        assert CalendarExportService._reminder_to_vevent(reminder) is None

    def test_basic_vevent(self):
        from apps.reminders.services.calendar_export_service import CalendarExportService
        reminder = MagicMock()
        reminder.id = 1
        reminder.due_at = timezone.now()
        reminder.content = "开庭"
        reminder.metadata = {}
        reminder.reminder_type = "hearing"
        reminder.contract_id = None
        reminder.case_id = None
        reminder.case_log_id = None
        vevent = CalendarExportService._reminder_to_vevent(reminder)
        assert vevent is not None

    def test_with_location(self):
        from apps.reminders.services.calendar_export_service import CalendarExportService
        reminder = MagicMock()
        reminder.id = 2
        reminder.due_at = timezone.now()
        reminder.content = "开庭"
        reminder.metadata = {"courtroom": "第三法庭"}
        reminder.reminder_type = "hearing"
        reminder.contract_id = None
        reminder.case_id = None
        reminder.case_log_id = None
        vevent = CalendarExportService._reminder_to_vevent(reminder)
        assert vevent is not None


# ---------------------------------------------------------------------------
# target_query
# ---------------------------------------------------------------------------

class TestTargetQuery:
    @pytest.mark.django_db
    def test_get_target_options_empty(self):
        from apps.reminders.services.target_query import get_target_options
        result = get_target_options(keyword="")
        assert "items" in result
        assert "groups" in result
