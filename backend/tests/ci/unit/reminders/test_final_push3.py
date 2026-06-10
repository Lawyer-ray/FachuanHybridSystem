"""Final push coverage tests for reminders module — validators, parser service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.core.exceptions import ValidationException


# ============================================================================
# reminders/services/validators.py tests
# ============================================================================


class TestNormalizeTargetId:
    def test_none_returns_none(self):
        from apps.reminders.services.validators import normalize_target_id

        assert normalize_target_id(None, field_name="id") is None

    def test_valid_positive_int(self):
        from apps.reminders.services.validators import normalize_target_id

        assert normalize_target_id(42, field_name="id") == 42

    def test_zero_raises(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(0, field_name="id")

    def test_negative_raises(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(-5, field_name="id")

    def test_bool_raises(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(True, field_name="id")

    def test_string_raises(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id("5", field_name="id")


class TestValidatePositiveId:
    def test_valid(self):
        from apps.reminders.services.validators import validate_positive_id

        validate_positive_id(1, field_name="id")  # no error

    def test_zero_raises(self):
        from apps.reminders.services.validators import validate_positive_id

        with pytest.raises(ValidationException):
            validate_positive_id(0, field_name="id")

    def test_bool_raises(self):
        from apps.reminders.services.validators import validate_positive_id

        with pytest.raises(ValidationException):
            validate_positive_id(True, field_name="id")


class TestValidateBindingExclusive:
    def test_no_binding(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)

    def test_single_binding(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)

    def test_multiple_bindings_raises(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        with pytest.raises(ValidationException):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)


class TestValidateFkExists:
    def test_contract_exists(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = True
        # Call with just contract_id and contract_target_query
        validate_fk_exists(
            contract_id=1, case_id=None, case_log_id=None,
            contract_target_query=mock_query,
        )
        mock_query.exists.assert_called_once_with(1)

    def test_contract_not_found(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException):
            validate_fk_exists(
                contract_id=99, case_id=None, case_log_id=None,
                contract_target_query=mock_query,
            )

    def test_case_exists(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = True
        validate_fk_exists(
            contract_id=None, case_id=1, case_log_id=None,
            case_target_query=mock_query,
        )

    def test_case_not_found(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException):
            validate_fk_exists(
                contract_id=None, case_id=99, case_log_id=None,
                case_target_query=mock_query,
            )

    def test_case_log_exists(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = True
        validate_fk_exists(
            contract_id=None, case_id=None, case_log_id=1,
            case_log_target_query=mock_query,
        )

    def test_case_log_not_found(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = Mock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException):
            validate_fk_exists(
                contract_id=None, case_id=None, case_log_id=99,
                case_log_target_query=mock_query,
            )

    def test_contract_query_missing_raises_runtime(self):
        from apps.reminders.services.validators import validate_fk_exists

        with pytest.raises(RuntimeError):
            validate_fk_exists(contract_id=1, case_id=None, case_log_id=None)

    def test_case_query_missing_raises_runtime(self):
        from apps.reminders.services.validators import validate_fk_exists

        with pytest.raises(RuntimeError):
            validate_fk_exists(contract_id=None, case_id=1, case_log_id=None)

    def test_case_log_query_missing_raises_runtime(self):
        from apps.reminders.services.validators import validate_fk_exists

        with pytest.raises(RuntimeError):
            validate_fk_exists(contract_id=None, case_id=None, case_log_id=1)


class TestNormalizeReminderType:
    def test_valid_type(self):
        from apps.reminders.services.validators import normalize_reminder_type

        result = normalize_reminder_type("hearing")
        assert result == "hearing"

    def test_empty_raises(self):
        from apps.reminders.services.validators import normalize_reminder_type

        with pytest.raises(ValidationException):
            normalize_reminder_type("")

    def test_invalid_type_raises(self):
        from apps.reminders.services.validators import normalize_reminder_type

        with pytest.raises(ValidationException):
            normalize_reminder_type("nonexistent_type")


class TestNormalizeContent:
    def test_valid_content(self):
        from apps.reminders.services.validators import normalize_content

        result = normalize_content("  开庭提醒  ")
        assert result == "开庭提醒"

    def test_empty_raises(self):
        from apps.reminders.services.validators import normalize_content

        with pytest.raises(ValidationException):
            normalize_content("")

    def test_too_long_raises(self):
        from apps.reminders.services.validators import normalize_content

        with pytest.raises(ValidationException):
            normalize_content("a" * 300)


class TestNormalizeDueAt:
    def test_naive_made_aware(self):
        from apps.reminders.services.validators import normalize_due_at

        naive = datetime(2024, 6, 15, 10, 0)
        result = normalize_due_at(naive)
        assert timezone.is_aware(result)

    def test_aware_preserved(self):
        from apps.reminders.services.validators import normalize_due_at

        aware = timezone.now()
        result = normalize_due_at(aware)
        assert result == aware

    def test_non_datetime_raises(self):
        from apps.reminders.services.validators import normalize_due_at

        with pytest.raises(ValidationException):
            normalize_due_at("2024-01-01")


class TestNormalizeMetadata:
    def test_none_returns_empty(self):
        from apps.reminders.services.validators import normalize_metadata

        assert normalize_metadata(None) == {}

    def test_valid_dict(self):
        from apps.reminders.services.validators import normalize_metadata

        meta = {"key": "value"}
        assert normalize_metadata(meta) == meta

    def test_non_dict_raises(self):
        from apps.reminders.services.validators import normalize_metadata

        with pytest.raises(ValidationException):
            normalize_metadata([1, 2, 3])

    def test_non_serializable_raises(self):
        from apps.reminders.services.validators import normalize_metadata

        with pytest.raises(ValidationException):
            normalize_metadata({"key": object()})


# ============================================================================
# reminders/services/reminder_parser_service.py tests
# ============================================================================


class TestInferReminderType:
    def test_hearing(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("请于2024年6月15日开庭") == "hearing"

    def test_asset_preservation(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("保全到期日2024年7月1日") == "asset_preservation_expires"

    def test_evidence_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("请在举证期限内提交") == "evidence_deadline"

    def test_appeal_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("上诉期限为15天") == "appeal_deadline"

    def test_statute_limitations(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("诉讼时效即将届满") == "statute_limitations"

    def test_payment_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("缴费期限为10天") == "payment_deadline"

    def test_submission_deadline(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("补正期限为7天") == "submission_deadline"

    def test_default_other(self):
        from apps.reminders.services.reminder_parser_service import _infer_reminder_type

        assert _infer_reminder_type("普通文本没有关键词") == "other"


class TestParseDate:
    def test_iso_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        result = _parse_date("2024-06-15")
        assert result == datetime(2024, 6, 15)

    def test_slash_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        result = _parse_date("2024/06/15")
        assert result == datetime(2024, 6, 15)

    def test_dot_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        result = _parse_date("2024.06.15")
        assert result == datetime(2024, 6, 15)

    def test_chinese_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        result = _parse_date("2024年6月15日")
        assert result == datetime(2024, 6, 15)

    def test_empty_string(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        assert _parse_date("") is None

    def test_none(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        assert _parse_date(None) is None

    def test_invalid_format(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        assert _parse_date("not a date") is None

    def test_fallback_regex_extraction(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        # Use a date with spaces between numbers: "2024年 6月 15日" won't match any format
        # but after stripping spaces becomes "2024年6月15日" which matches "%Y年%m月%d日"
        # For a real fallback, use something like date separated by Chinese chars that don't match
        result = _parse_date("2024--6--15")
        # "2024--6--15" -> normalized: "2024--6--15"
        # Won't match any format, regex finds ["2024", "6", "15"]
        assert result == datetime(2024, 6, 15)


class TestExtractTimeNearDate:
    def test_afternoon_time(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date

        text = "2024年6月15日下午3点开庭"
        # date ends at index of "下" after the date
        date_part = "2024年6月15日"
        result = _extract_time_near_date(text, len(date_part))
        assert result is not None
        hour, minute = result
        assert hour == 15
        assert minute == 0

    def test_morning_time(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date

        text = "2024年6月15日上午9点30分开庭"
        date_part = "2024年6月15日"
        result = _extract_time_near_date(text, len(date_part))
        assert result is not None
        hour, minute = result
        assert hour == 9
        assert minute == 30

    def test_half_hour(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date

        text = "2024年6月15日下午3点半"
        date_part = "2024年6月15日"
        result = _extract_time_near_date(text, len(date_part))
        assert result is not None
        assert result == (15, 30)

    def test_no_time(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date

        text = "2024年6月15日开庭"
        date_part = "2024年6月15日"
        result = _extract_time_near_date(text, len(date_part))
        # "开庭" doesn't match time pattern
        assert result is None

    def test_late_night(self):
        from apps.reminders.services.reminder_parser_service import _extract_time_near_date

        text = "2024年6月15日晚间8点"
        date_part = "2024年6月15日"
        result = _extract_time_near_date(text, len(date_part))
        assert result is not None
        assert result[0] == 20  # 8PM


class TestExtractSentence:
    def test_basic_extraction(self):
        from apps.reminders.services.reminder_parser_service import _extract_sentence

        text = "第一句话。第二句话有日期。第三句话。"
        result = _extract_sentence(text, 7, 16)
        assert "日期" in result or "第二句" in result

    def test_start_of_text(self):
        from apps.reminders.services.reminder_parser_service import _extract_sentence

        text = "开头句子有日期"
        result = _extract_sentence(text, 0, 4)
        assert result  # non-empty


class TestGenerateContent:
    def test_short_sentence(self):
        from apps.reminders.services.reminder_parser_service import _generate_content

        result = _generate_content("开庭日期已确定", "开庭", datetime(2024, 6, 15))
        assert "开庭" in result
        assert "开庭日期已确定" in result

    def test_long_sentence_truncated(self):
        from apps.reminders.services.reminder_parser_service import _generate_content

        long = "a" * 100
        result = _generate_content(long, "开庭", datetime(2024, 6, 15))
        assert "…" in result
        assert len(result) < 120


class TestParseRemindersFromText:
    def test_empty_text(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text

        assert parse_reminders_from_text("") == []
        assert parse_reminders_from_text(None) == []
        assert parse_reminders_from_text("   ") == []

    def test_text_with_date_and_hearing(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text

        text = "请于2024年6月15日开庭审理本案"
        results = parse_reminders_from_text(text)
        assert len(results) >= 1
        assert results[0].reminder_type == "hearing"
        assert "2024-06-15" in results[0].due_at

    def test_text_with_multiple_dates(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text

        text = "2024年6月15日开庭，2024年7月1日举证期限届满"
        results = parse_reminders_from_text(text)
        assert len(results) >= 2

    def test_text_no_dates(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text

        text = "今天天气不错，没有日期信息"
        results = parse_reminders_from_text(text)
        assert len(results) == 0

    def test_duplicate_dates_deduplicated(self):
        from apps.reminders.services.reminder_parser_service import parse_reminders_from_text

        text = "2024年6月15日开庭，2024年6月15日注意"
        results = parse_reminders_from_text(text)
        assert len(results) == 1
