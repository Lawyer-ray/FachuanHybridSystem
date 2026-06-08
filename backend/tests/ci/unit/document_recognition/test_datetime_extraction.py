"""测试开庭时间提取 Mixin 的纯逻辑方法

覆盖: _datetime_extraction_mixin.py
重点: 日期解析、上下文评分、合理性校验、最佳时间选择
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from apps.document_recognition.services._datetime_extraction_mixin import (
    DATETIME_PATTERNS,
    HEARING_CONTEXT_KEYWORDS,
    HEARING_HIGH_WEIGHT_KEYWORDS,
    HEARING_LOW_WEIGHT_KEYWORDS,
    HEARING_MEDIUM_WEIGHT_KEYWORDS,
    DatetimeExtractionMixin,
)


@pytest.fixture
def mixin() -> DatetimeExtractionMixin:
    return DatetimeExtractionMixin()


# ============================================================
# _parse_datetime_groups
# ============================================================


class TestParseDatetimeGroups:
    """测试正则分组解析为 datetime"""

    def test_am_pm_morning(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "上午", "9", "30"), True, "test")
        assert result == datetime(2026, 6, 15, 9, 30)

    def test_am_pm_afternoon_converts(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "下午", "2", "30"), True, "test")
        assert result == datetime(2026, 6, 15, 14, 30)

    def test_am_pm_afternoon_12_no_convert(self, mixin: DatetimeExtractionMixin) -> None:
        """下午12点不加12"""
        result = mixin._parse_datetime_groups(("2026", "6", "15", "下午", "12", "0"), True, "test")
        assert result == datetime(2026, 6, 15, 12, 0)

    def test_am_pm_morning_12_converts_to_0(self, mixin: DatetimeExtractionMixin) -> None:
        """上午12点应转为0点"""
        result = mixin._parse_datetime_groups(("2026", "6", "15", "上午", "12", "0"), True, "test")
        assert result == datetime(2026, 6, 15, 0, 0)

    def test_no_am_pm_5_groups(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "14", "30"), False, "test")
        assert result == datetime(2026, 6, 15, 14, 30)

    def test_invalid_am_pm_label(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "晚上", "9", "30"), True, "test")
        assert result is None

    def test_wrong_group_count(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15"), True, "test")
        assert result is None

    def test_invalid_month(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "13", "15", "14", "30"), False, "test")
        assert result is None

    def test_invalid_day(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "32", "14", "30"), False, "test")
        assert result is None

    def test_invalid_hour(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "25", "30"), False, "test")
        assert result is None

    def test_invalid_minute(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2026", "6", "15", "14", "60"), False, "test")
        assert result is None

    def test_year_too_old(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2019", "6", "15", "14", "30"), False, "test")
        assert result is None

    def test_year_too_far_future(self, mixin: DatetimeExtractionMixin) -> None:
        result = mixin._parse_datetime_groups(("2031", "6", "15", "14", "30"), False, "test")
        assert result is None

    def test_valid_year_range(self, mixin: DatetimeExtractionMixin) -> None:
        for year in (2020, 2025, 2030):
            result = mixin._parse_datetime_groups((str(year), "1", "1", "0", "0"), False, "test")
            assert result is not None
            assert result.year == year


# ============================================================
# _calculate_context_score
# ============================================================


class TestCalculateContextScore:
    """测试上下文评分"""

    def test_high_weight_keyword(self, mixin: DatetimeExtractionMixin) -> None:
        text = "本院定于2026年6月15日上午9时30分开庭审理"
        score = mixin._calculate_context_score(text, 28)
        assert score >= 25  # "开庭" 是高权重

    def test_medium_weight_keyword(self, mixin: DatetimeExtractionMixin) -> None:
        text = "请于2026年6月15日准时到庭"
        score = mixin._calculate_context_score(text, 24)
        assert score >= 15

    def test_no_keywords(self, mixin: DatetimeExtractionMixin) -> None:
        text = "某个时间2026年6月15日某处"
        score = mixin._calculate_context_score(text, 10)
        assert score == 0

    def test_multiple_keywords_cumulative(self, mixin: DatetimeExtractionMixin) -> None:
        text = "定于2026年6月15日开庭审理，请准时到庭参加诉讼"
        score = mixin._calculate_context_score(text, 28)
        assert score > 25  # 多个关键词累计

    def test_score_capped_at_100(self, mixin: DatetimeExtractionMixin) -> None:
        text = "开庭" * 20 + "2026年6月15日" + "庭审" * 20
        score = mixin._calculate_context_score(text, 40)
        assert score <= 100


# ============================================================
# _score_days_diff
# ============================================================


class TestScoreDaysDiff:
    """测试天数差评分"""

    def test_far_past_decreases_score(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(-10, 50, [])
        assert score == 20  # 50 - 30
        assert "已过去" in reasons[0]

    def test_recent_past_slight_penalty(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(-3, 50, [])
        assert score == 40  # 50 - 10

    def test_near_future_bonus(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(30, 50, [])
        assert score == 70  # 50 + 20

    def test_one_year_out_penalty(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(400, 50, [])
        assert score == 35  # 50 - 15

    def test_two_years_out_heavy_penalty(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(800, 50, [])
        assert score == 10  # 50 - 40

    def test_six_months_out_slight_penalty(self, mixin: DatetimeExtractionMixin) -> None:
        score, reasons = mixin._score_days_diff(200, 50, [])
        assert score == 45  # 50 - 5


# ============================================================
# _validate_hearing_datetime
# ============================================================


class TestValidateHearingDatetime:
    """测试开庭时间合理性校验"""

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_workday_worktime_full_hour(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)  # Monday
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # 2026-06-15 is Monday, 9:00 AM
        dt = datetime(2026, 6, 15, 9, 0)
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert is_valid is True
        assert "工作时间内" in reasons
        assert "整点/半点" in reasons
        assert "工作日" in reasons

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_weekend_penalty(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # 2026-06-13 is Saturday
        dt = datetime(2026, 6, 13, 9, 0)
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert "周末" in reasons

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_non_worktime_penalty(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        dt = datetime(2026, 6, 15, 2, 0)
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert "非工作时间" in reasons

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_edge_worktime(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        dt = datetime(2026, 6, 15, 7, 30)
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert "边缘工作时间" in reasons

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_quarter_hour_bonus(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        dt = datetime(2026, 6, 15, 9, 15)
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert "刻钟" in reasons

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_score_clamped_to_0_100(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # Far past + non-worktime + weekend => score should be clamped to 0
        dt = datetime(2020, 1, 4, 2, 0)  # Saturday, 2am, 6 years ago
        is_valid, score, reasons = mixin._validate_hearing_datetime(dt)
        assert score == 0


# ============================================================
# _select_best_datetime
# ============================================================


class TestSelectBestDatetime:
    """测试最佳时间选择逻辑"""

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_no_results_returns_none(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result, reason = mixin._select_best_datetime([], None)
        assert result is None
        assert reason == "无法提取"

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_only_ollama_valid(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        ollama_dt = datetime(2026, 6, 15, 9, 0)
        result, reason = mixin._select_best_datetime([], ollama_dt)
        assert result == ollama_dt
        assert "ollama" in reason

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_regex_wins_over_ollama(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        regex_dt = datetime(2026, 6, 15, 9, 0)
        ollama_dt = datetime(2026, 7, 20, 10, 0)
        regex_results = [(regex_dt, "2026年6月15日上午9时0分", 80)]
        result, reason = mixin._select_best_datetime(regex_results, ollama_dt)
        assert result == regex_dt

    @patch("apps.document_recognition.services._datetime_extraction_mixin.datetime")
    def test_regex_and_ollama_agree(self, mock_dt: type, mixin: DatetimeExtractionMixin) -> None:
        mock_dt.now.return_value = datetime(2026, 6, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        dt = datetime(2026, 6, 15, 9, 0)
        regex_results = [(dt, "2026年6月15日上午9时0分", 80)]
        result, reason = mixin._select_best_datetime(regex_results, dt)
        assert result == dt
        assert "一致" in reason


# ============================================================
# DATETIME_PATTERNS
# ============================================================


class TestDatetimePatterns:
    """测试正则模式常量定义"""

    def test_patterns_not_empty(self) -> None:
        assert len(DATETIME_PATTERNS) > 0

    def test_each_pattern_is_tuple(self) -> None:
        for pattern, has_am_pm in DATETIME_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(has_am_pm, bool)

    def test_keywords_defined(self) -> None:
        assert len(HEARING_HIGH_WEIGHT_KEYWORDS) > 0
        assert len(HEARING_MEDIUM_WEIGHT_KEYWORDS) > 0
        assert len(HEARING_LOW_WEIGHT_KEYWORDS) > 0
        assert len(HEARING_CONTEXT_KEYWORDS) > 0

    def test_context_keywords_is_union(self) -> None:
        """HEARING_CONTEXT_KEYWORDS 应该是三个子列表的并集"""
        assert set(HEARING_CONTEXT_KEYWORDS) == (
            set(HEARING_HIGH_WEIGHT_KEYWORDS)
            | set(HEARING_MEDIUM_WEIGHT_KEYWORDS)
            | set(HEARING_LOW_WEIGHT_KEYWORDS)
        )
