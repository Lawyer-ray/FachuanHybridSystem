"""Coverage tests for reminders/services/reminder_parser_service.py."""
from __future__ import annotations

import pytest

from apps.reminders.services.reminder_parser_service import (
    _infer_reminder_type,
    _parse_date,
    _extract_time_near_date,
    _extract_sentence,
    _generate_content,
    parse_reminders_from_text,
    DEFAULT_REMINDER_TYPE,
    REMINDER_TYPE_LABELS,
)


class TestInferReminderType:
    def test_hearing(self):
        assert _infer_reminder_type("2024年6月15日开庭") == "hearing"

    def test_summons(self):
        assert _infer_reminder_type("收到传票") == "hearing"

    def test_asset_preservation(self):
        assert _infer_reminder_type("保全到期2024年7月") == "asset_preservation_expires"

    def test_evidence_deadline(self):
        assert _infer_reminder_type("举证期限到6月底") == "evidence_deadline"

    def test_appeal_deadline(self):
        assert _infer_reminder_type("上诉期限15天") == "appeal_deadline"

    def test_statute_limitations(self):
        assert _infer_reminder_type("诉讼时效3年") == "statute_limitations"

    def test_payment_deadline(self):
        assert _infer_reminder_type("缴费期限") == "payment_deadline"

    def test_submission_deadline(self):
        assert _infer_reminder_type("补正期限") == "submission_deadline"

    def test_default_other(self):
        assert _infer_reminder_type("普通文本") == DEFAULT_REMINDER_TYPE


class TestParseDate:
    def test_yyyy_mm_dd(self):
        result = _parse_date("2024-06-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_yyyy_slash_mm_slash_dd(self):
        result = _parse_date("2024/06/15")
        assert result is not None
        assert result.month == 6

    def test_yyyy_dot_mm_dot_dd(self):
        result = _parse_date("2024.06.15")
        assert result is not None

    def test_chinese_format(self):
        result = _parse_date("2024年6月15日")
        assert result is not None
        assert result.day == 15

    def test_empty_returns_none(self):
        assert _parse_date("") is None

    def test_invalid_date(self):
        assert _parse_date("not a date") is None

    def test_fallback_regex(self):
        result = _parse_date("2024年13月32日")
        assert result is None  # Invalid month/day


class TestExtractTimeNearDate:
    def test_afternoon_time(self):
        text = "2024年6月15日下午3点开庭"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is not None
        assert result[0] == 15

    def test_morning_time(self):
        text = "2024年6月15日上午9点半开庭"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is not None
        assert result == (9, 30)

    def test_no_time(self):
        text = "2024年6月15日开庭"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is None

    def test_late_night(self):
        text = "2024年6月15日晚间8时30分开庭"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is not None
        assert result[0] == 20
        assert result[1] == 30

    def test_midnight_hour(self):
        text = "2024年6月15日凌晨0点"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is not None
        assert result[0] == 0

    def test_24_hour_format(self):
        text = "2024年6月15日15时30分开庭"
        result = _extract_time_near_date(text, text.index("15日") + len("15日"))
        assert result is not None
        assert result[0] == 15
        assert result[1] == 30


class TestExtractSentence:
    def test_basic_extraction(self):
        text = "前文。目标句子包含日期。后文。"
        result = _extract_sentence(text, 3, 15)
        assert "目标句子" in result

    def test_at_start(self):
        text = "目标句子包含日期。后文。"
        result = _extract_sentence(text, 0, 10)
        assert len(result) > 0

    def test_at_end(self):
        text = "前文。目标句子"
        result = _extract_sentence(text, 4, len(text))
        assert len(result) > 0


class TestGenerateContent:
    def test_normal(self):
        result = _generate_content("开庭传票", "开庭", None)  # type: ignore[arg-type]
        assert "开庭" in result

    def test_long_sentence_truncated(self):
        long = "x" * 100
        result = _generate_content(long, "开庭", None)  # type: ignore[arg-type]
        assert "…" in result
        assert len(result) < 120


class TestParseRemindersFromText:
    def test_empty_text(self):
        assert parse_reminders_from_text("") == []
        assert parse_reminders_from_text("   ") == []

    def test_no_dates(self):
        assert parse_reminders_from_text("没有日期的文本") == []

    def test_single_date(self):
        text = "2024年6月15日开庭传票，请准时到庭。"
        results = parse_reminders_from_text(text)
        assert len(results) == 1
        assert results[0].reminder_type == "hearing"
        assert "2024-06-15" in results[0].due_at

    def test_multiple_dates(self):
        text = "2024年6月15日开庭。2024年7月20日举证期限。"
        results = parse_reminders_from_text(text)
        assert len(results) >= 2

    def test_deduplication(self):
        text = "2024年6月15日开庭。2024年6月15日再次提到。"
        results = parse_reminders_from_text(text)
        assert len(results) == 1

    def test_with_time(self):
        text = "2024年6月15日下午3点开庭传票。"
        results = parse_reminders_from_text(text)
        assert len(results) == 1
        assert "15:00" in results[0].due_at

    def test_default_time_9am(self):
        text = "2024年6月15日开庭传票。"
        results = parse_reminders_from_text(text)
        assert "09:00" in results[0].due_at


class TestReminderTypeLabels:
    def test_all_types_have_labels(self):
        for t in ["hearing", "asset_preservation_expires", "evidence_deadline",
                  "appeal_deadline", "statute_limitations", "payment_deadline",
                  "submission_deadline", "other"]:
            assert t in REMINDER_TYPE_LABELS
