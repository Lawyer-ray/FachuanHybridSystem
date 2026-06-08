"""财产保全日期提取服务测试。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.preservation_date.services.extraction_service import PreservationDateExtractionService


class TestPreservationDateExtractionService:
    """可测试的纯函数和逻辑分支。"""

    def _make_service(self):
        return PreservationDateExtractionService(text_service=MagicMock())

    # ── _preprocess_text ──

    def test_preprocess_text_removes_null_chars(self):
        svc = self._make_service()
        result = svc._preprocess_text("hello\x00world")
        assert "\x00" not in result

    def test_preprocess_text_removes_replacement_chars(self):
        svc = self._make_service()
        result = svc._preprocess_text("hello�world")
        assert "�" not in result

    def test_preprocess_text_normalizes_whitespace(self):
        svc = self._make_service()
        result = svc._preprocess_text("hello   world")
        assert "   " not in result
        assert "hello world" in result

    def test_preprocess_text_preserves_newlines(self):
        svc = self._make_service()
        result = svc._preprocess_text("line1\nline2")
        assert "\n" in result

    def test_preprocess_text_collapses_multiple_newlines(self):
        svc = self._make_service()
        result = svc._preprocess_text("line1\n\n\n\nline2")
        assert "\n\n" not in result

    def test_preprocess_text_fullwidth_to_halfwidth(self):
        svc = self._make_service()
        result = svc._preprocess_text("你好，世界。")
        assert "," in result
        assert "." in result

    def test_preprocess_text_preserves_date_chars(self):
        svc = self._make_service()
        result = svc._preprocess_text("2025年1月15日")
        assert "年" in result
        assert "月" in result
        assert "日" in result

    def test_preprocess_text_truncates_long_text(self):
        svc = self._make_service()
        long_text = "a" * 10000
        result = svc._preprocess_text(long_text)
        assert len(result) <= svc._MAX_TEXT_LENGTH

    def test_preprocess_text_strips(self):
        svc = self._make_service()
        result = svc._preprocess_text("  hello  ")
        assert result == "hello"

    # ── _parse_date ──

    def test_parse_date_iso_format(self):
        svc = self._make_service()
        result = svc._parse_date("2025-01-15")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_chinese_format(self):
        svc = self._make_service()
        result = svc._parse_date("2025年1月15日")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_slash_format(self):
        svc = self._make_service()
        result = svc._parse_date("2025/1/15")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_dot_format(self):
        svc = self._make_service()
        result = svc._parse_date("2025.1.15")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_range_cn(self):
        svc = self._make_service()
        result = svc._parse_date("2025年1月15日至2026年1月14日")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_range_dash(self):
        svc = self._make_service()
        result = svc._parse_date("2025.1.15-2026.1.14")
        assert result == datetime(2025, 1, 15)

    def test_parse_date_none(self):
        svc = self._make_service()
        assert svc._parse_date(None) is None

    def test_parse_date_null_string(self):
        svc = self._make_service()
        assert svc._parse_date("null") is None

    def test_parse_date_empty(self):
        svc = self._make_service()
        assert svc._parse_date("") is None

    def test_parse_date_fallback_numbers(self):
        svc = self._make_service()
        result = svc._parse_date("2025年1月15日")
        assert result is not None

    def test_parse_date_invalid(self):
        svc = self._make_service()
        result = svc._parse_date("not a date")
        assert result is None

    # ── _parse_chinese_date ──

    def test_parse_chinese_date_basic(self):
        svc = self._make_service()
        result = svc._parse_chinese_date("二〇二五年三月十五日")
        assert result == datetime(2025, 3, 15)

    def test_parse_chinese_date_ten(self):
        svc = self._make_service()
        result = svc._parse_chinese_date("二〇二五年十二月二十日")
        assert result == datetime(2025, 12, 20)

    def test_parse_chinese_date_not_chinese(self):
        svc = self._make_service()
        result = svc._parse_chinese_date("2025年1月15日")
        assert result is None  # no chinese digits

    # ── _cn_to_year ──

    def test_cn_to_year_basic(self):
        cn_map = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
        assert PreservationDateExtractionService._cn_to_year("二〇二五", cn_map) == 2025

    def test_cn_to_year_with_arabic(self):
        cn_map = {"〇": 0, "二": 2, "五": 5}
        assert PreservationDateExtractionService._cn_to_year("2025", cn_map) == 2025

    # ── _cn_to_number ──

    def test_cn_to_number_single(self):
        cn_map = {"一": 1, "二": 2, "三": 3, "五": 5, "十": 10}
        assert PreservationDateExtractionService._cn_to_number("三", cn_map) == 3

    def test_cn_to_number_ten(self):
        cn_map = {"一": 1, "二": 2, "三": 3, "五": 5, "十": 10}
        assert PreservationDateExtractionService._cn_to_number("十五", cn_map) == 15

    def test_cn_to_number_twenty(self):
        cn_map = {"二": 2, "十": 10}
        assert PreservationDateExtractionService._cn_to_number("二十", cn_map) == 20

    def test_cn_to_number_twenty_five(self):
        cn_map = {"二": 2, "五": 5, "十": 10}
        assert PreservationDateExtractionService._cn_to_number("二十五", cn_map) == 25

    def test_cn_to_number_ten_alone(self):
        cn_map = {"十": 10}
        assert PreservationDateExtractionService._cn_to_number("十", cn_map) == 10

    def test_cn_to_number_arabic(self):
        cn_map = {}
        assert PreservationDateExtractionService._cn_to_number("15", cn_map) == 15

    # ── _fix_pending_measure_type ──

    def test_fix_pending_freeze(self):
        assert PreservationDateExtractionService._fix_pending_measure_type("冻结") == "轮候冻结"

    def test_fix_pending_seizure(self):
        assert PreservationDateExtractionService._fix_pending_measure_type("查封") == "轮候查封"

    def test_fix_pending_unknown(self):
        assert PreservationDateExtractionService._fix_pending_measure_type("扣押") == "轮候扣押"

    # ── _parse_measure_item ──

    def test_parse_measure_item_missing_type(self):
        svc = self._make_service()
        result = svc._parse_measure_item({"property_description": "房产"})
        assert result is None

    def test_parse_measure_item_missing_description(self):
        svc = self._make_service()
        result = svc._parse_measure_item({"measure_type": "冻结"})
        assert result is None

    def test_parse_measure_item_normal(self):
        svc = self._make_service()
        result = svc._parse_measure_item({
            "measure_type": "冻结",
            "property_description": "银行存款",
            "end_date": "2025-12-31",
        })
        assert result is not None
        assert result.measure_type == "冻结"
        assert result.is_pending is False

    def test_parse_measure_item_pending_by_type(self):
        svc = self._make_service()
        result = svc._parse_measure_item({
            "measure_type": "轮候冻结",
            "property_description": "银行存款",
        })
        assert result is not None
        assert result.is_pending is True
        assert result.end_date is None

    def test_parse_measure_item_pending_by_raw_text(self):
        svc = self._make_service()
        result = svc._parse_measure_item({
            "measure_type": "冻结",
            "property_description": "银行存款",
            "raw_text": "轮候冻结银行存款",
        })
        assert result is not None
        assert result.is_pending is True
        assert "轮候" in result.measure_type

    # ── _extract_json ──

    def test_extract_json_code_block(self):
        svc = self._make_service()
        text = '```json\n{"measures": []}\n```'
        result = svc._extract_json(text)
        assert result == '{"measures": []}'

    def test_extract_json_brace_object(self):
        svc = self._make_service()
        text = 'result: {"measures": []}'
        result = svc._extract_json(text)
        assert result is not None

    def test_extract_json_array(self):
        svc = self._make_service()
        text = "result: [1, 2, 3]"
        result = svc._extract_json(text)
        assert result is not None

    def test_extract_json_empty(self):
        svc = self._make_service()
        assert svc._extract_json("") is None
        assert svc._extract_json("   ") is None

    # ── _fix_json ──

    def test_fix_json_trailing_comma_array(self):
        svc = self._make_service()
        result = svc._fix_json("[1, 2, 3,]")
        assert "1" in result
        assert result.rstrip().endswith("]")

    def test_fix_json_trailing_comma_object(self):
        svc = self._make_service()
        result = svc._fix_json('{"a": 1, "b": 2,}')
        import json
        parsed = json.loads(result)
        assert parsed["a"] == 1

    # ── _replace_single_quotes ──

    def test_replace_single_quotes_simple(self):
        result = PreservationDateExtractionService._replace_single_quotes("{'key': 'value'}")
        import json
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_replace_single_quotes_apostrophe_preserved(self):
        text = '{"name": "it\'s test"}'
        result = PreservationDateExtractionService._replace_single_quotes(text)
        assert "it's" in result

    # ── _is_valid_json ──

    def test_is_valid_json_true(self):
        svc = self._make_service()
        assert svc._is_valid_json('{"a": 1}') is True

    def test_is_valid_json_false(self):
        svc = self._make_service()
        assert svc._is_valid_json("{invalid") is False

    # ── _build_reminder_content ──

    def test_build_reminder_content_with_date(self):
        svc = self._make_service()
        from apps.preservation_date.services.models import PreservationMeasure

        m = PreservationMeasure(
            measure_type="冻结",
            property_description="银行存款",
            end_date=datetime(2025, 12, 31),
        )
        content = svc._build_reminder_content(m)
        assert "银行存款" in content
        assert "2025年12月31日" in content

    def test_build_reminder_content_pending(self):
        svc = self._make_service()
        from apps.preservation_date.services.models import PreservationMeasure

        m = PreservationMeasure(
            measure_type="轮候冻结",
            property_description="银行存款",
            is_pending=True,
        )
        content = svc._build_reminder_content(m)
        assert "轮候状态" in content

    # ── to_reminder_format ──

    def test_to_reminder_format_with_end_date(self):
        svc = self._make_service()
        from apps.preservation_date.services.models import PreservationMeasure

        measures = [
            PreservationMeasure(
                measure_type="冻结",
                property_description="银行存款",
                end_date=datetime(2025, 12, 31),
            )
        ]
        reminders = svc.to_reminder_format(measures)
        assert len(reminders) == 1
        assert reminders[0].due_at == datetime(2025, 12, 31)

    def test_to_reminder_format_no_end_date(self):
        svc = self._make_service()
        from apps.preservation_date.services.models import PreservationMeasure

        measures = [
            PreservationMeasure(
                measure_type="轮候冻结",
                property_description="银行存款",
            )
        ]
        reminders = svc.to_reminder_format(measures)
        assert len(reminders) == 0

    def test_to_reminder_format_empty(self):
        svc = self._make_service()
        assert svc.to_reminder_format([]) == []

    # ── extract_from_text ──

    def test_extract_from_text_empty(self):
        svc = self._make_service()
        result = svc.extract_from_text("")
        assert result.success is False
        assert "空" in result.error

    def test_extract_from_text_whitespace_only(self):
        svc = self._make_service()
        result = svc.extract_from_text("   ")
        assert result.success is False
