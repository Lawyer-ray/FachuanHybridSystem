"""Tests for preservation_date.services.rule_engine."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.preservation_date.services.rule_engine import (
    PreservationRuleEngine,
    RuleMatch,
    extract_with_rules,
)
from apps.preservation_date.services.models import PreservationMeasure


class TestRuleMatch:
    def test_creation(self) -> None:
        rm = RuleMatch(
            measure_type="冻结",
            property_description="银行存款",
            raw_text="冻结银行存款",
        )
        assert rm.measure_type == "冻结"
        assert rm.start_date is None
        assert rm.is_pending is False


class TestPreservationRuleEngineInit:
    def test_init(self) -> None:
        engine = PreservationRuleEngine()
        assert len(engine._pending_patterns) == 3
        assert len(engine._formal_patterns) == 5


class TestSegmentText:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_empty_text(self) -> None:
        assert self.engine._segment_text("") == []

    def test_single_paragraph(self) -> None:
        result = self.engine._segment_text("这是一段较长的测试文本，用于验证分段功能是否正常。")
        assert len(result) >= 1

    def test_multiple_paragraphs(self) -> None:
        text = "第一段较长的测试文本，用于验证分段。\n第二段较长的测试文本，用于验证分段。"
        result = self.engine._segment_text(text)
        assert len(result) >= 2

    def test_short_segments_filtered(self) -> None:
        result = self.engine._segment_text("短。\n很长的段落文本内容，超过了五个字符的限制。")
        assert all(len(s) > 5 for s in result)


class TestIsOverlapping:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_no_overlap(self) -> None:
        assert self.engine._is_overlapping((0, 5), [(10, 15)]) is False

    def test_overlap(self) -> None:
        assert self.engine._is_overlapping((0, 10), [(5, 15)]) is True

    def test_adjacent_no_overlap(self) -> None:
        assert self.engine._is_overlapping((0, 5), [(5, 10)]) is False

    def test_empty_spans(self) -> None:
        assert self.engine._is_overlapping((0, 5), []) is False


class TestCleanPropertyDesc:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_removes_applicant_prefix(self) -> None:
        result = self.engine._clean_property_desc("被申请人的银行存款")
        assert "被申请人" not in result

    def test_strips_punctuation(self) -> None:
        result = self.engine._clean_property_desc("银行存款，")
        assert not result.endswith("，")

    def test_strips_whitespace(self) -> None:
        result = self.engine._clean_property_desc("  银行存款  ")
        assert result == "银行存款"


class TestExtractDates:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_date_range(self) -> None:
        text = "自2024年1月1日起至2024年12月31日止"
        dates = self.engine._extract_dates(text)
        assert len(dates) == 2
        assert "2024" in dates[0]
        assert "2024" in dates[1]

    def test_single_date(self) -> None:
        text = "于2024年6月15日查封"
        dates = self.engine._extract_dates(text)
        assert len(dates) >= 1

    def test_no_dates(self) -> None:
        dates = self.engine._extract_dates("没有日期的文本")
        assert dates == []

    def test_after_position(self) -> None:
        text = "前期2024年1月1日 后期2024年6月1日"
        dates = self.engine._extract_dates(text, after_pos=10)
        assert len(dates) >= 1


class TestExtractDuration:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_duration_years(self) -> None:
        result = self.engine._extract_duration("期限为三年")
        assert result is not None
        assert "三" in result

    def test_duration_months(self) -> None:
        result = self.engine._extract_duration("有效期为六个月")
        assert result is not None

    def test_no_duration(self) -> None:
        result = self.engine._extract_duration("这是一段没有期限的文本")
        assert result is None


class TestParseDate:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_dash_format(self) -> None:
        result = self.engine._parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_slash_format(self) -> None:
        result = self.engine._parse_date("2024/01/15")
        assert result == datetime(2024, 1, 15)

    def test_dot_format(self) -> None:
        result = self.engine._parse_date("2024.01.15")
        assert result == datetime(2024, 1, 15)

    def test_chinese_format(self) -> None:
        result = self.engine._parse_date("2024年1月15日")
        assert result == datetime(2024, 1, 15)

    def test_none_returns_none(self) -> None:
        assert self.engine._parse_date(None) is None

    def test_empty_returns_none(self) -> None:
        assert self.engine._parse_date("") is None

    def test_invalid_returns_none(self) -> None:
        assert self.engine._parse_date("not a date") is None


class TestCalculateEndDate:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_years(self) -> None:
        start = datetime(2024, 1, 1)
        result = self.engine._calculate_end_date(start, "3年")
        assert result is not None
        assert result.year == 2026
        # Should be one day before anniversary
        assert result.month == 12
        assert result.day == 31

    def test_months(self) -> None:
        start = datetime(2024, 1, 15)
        result = self.engine._calculate_end_date(start, "6个月")
        assert result is not None
        assert result.month == 7

    def test_chinese_number_no_match(self) -> None:
        start = datetime(2024, 1, 1)
        result = self.engine._calculate_end_date(start, "三年")
        # Chinese number not matched by regex
        assert result is None

    def test_days(self) -> None:
        start = datetime(2024, 1, 1)
        result = self.engine._calculate_end_date(start, "30天")
        assert result is not None
        assert result.day == 30

    def test_no_number(self) -> None:
        start = datetime(2024, 1, 1)
        result = self.engine._calculate_end_date(start, "长期")
        assert result is None


class TestDeduplicate:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_dedup_same(self) -> None:
        measures = [
            PreservationMeasure(measure_type="冻结", property_description="银行存款"),
            PreservationMeasure(measure_type="冻结", property_description="银行存款"),
        ]
        result = self.engine._deduplicate(measures)
        assert len(result) == 1

    def test_dedup_different(self) -> None:
        measures = [
            PreservationMeasure(measure_type="冻结", property_description="银行存款"),
            PreservationMeasure(measure_type="查封", property_description="房产"),
        ]
        result = self.engine._deduplicate(measures)
        assert len(result) == 2


class TestExtract:
    def setup_method(self) -> None:
        self.engine = PreservationRuleEngine()

    def test_empty_text(self) -> None:
        assert self.engine.extract("") == []
        assert self.engine.extract("   ") == []
        assert self.engine.extract(None) == []

    def test_extract_freeze(self) -> None:
        text = "冻结被申请人银行存款500000元，自2024年1月1日起至2024年12月31日止。"
        result = self.engine.extract(text)
        # Should find at least one freeze measure
        assert len(result) >= 1
        assert any(m.measure_type == "冻结" for m in result)

    def test_extract_pending_freeze(self) -> None:
        text = "轮候冻结被申请人银行账户内的存款。"
        result = self.engine.extract(text)
        assert any(m.is_pending is True for m in result)

    def test_no_measures(self) -> None:
        text = "本案不涉及财产保全措施。原告主张被告支付货款。"
        result = self.engine.extract(text)
        assert result == []


class TestExtractWithRules:
    def test_convenience_function(self) -> None:
        text = "冻结被申请人银行存款500000元。"
        result = extract_with_rules(text)
        assert isinstance(result, list)
