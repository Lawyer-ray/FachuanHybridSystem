"""Unit tests for validate_advisor_contract_title_dates."""

from __future__ import annotations

from datetime import date

import pytest

from apps.contracts.domain.validators import validate_advisor_contract_title_dates
from apps.core.exceptions import ValidationException

# ---------------------------------------------------------------------------
# 非顾问合同 → 跳过校验
# ---------------------------------------------------------------------------


def test_non_advisor_skipped() -> None:
    """非顾问合同不做标题日期校验，即使标题/日期明显不匹配也不报错。"""
    validate_advisor_contract_title_dates(
        case_type="civil",
        title="2024-2025年度 某某合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


# ---------------------------------------------------------------------------
# 缺少字段 → 跳过校验
# ---------------------------------------------------------------------------


def test_missing_title_skipped() -> None:
    """没有标题时跳过校验。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title=None,
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_missing_dates_skipped() -> None:
    """没有日期时跳过校验。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司常法顾问-2026年8月12日至2027年8月11日",
        start_date=None,
        end_date=None,
    )


# ---------------------------------------------------------------------------
# 标题无日期信息 → 跳过校验
# ---------------------------------------------------------------------------


def test_no_date_in_title_skipped() -> None:
    """标题中不含任何日期信息时跳过校验。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司常法顾问合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


# ---------------------------------------------------------------------------
# 完整中文日期格式
# ---------------------------------------------------------------------------


def test_full_chinese_date_correct() -> None:
    """标题中的完整中文日期与实际日期完全一致 → 通过。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司常法顾问-2026年8月12日至2027年8月11日",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_full_chinese_date_correct_padded() -> None:
    """带零填充的日期也能正确解析。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司常法顾问-2026年08月12日至2027年08月11日",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_full_chinese_date_wrong_start() -> None:
    """标题开始日期比实际早一年 → 报错。"""
    with pytest.raises(ValidationException, match="开始日期"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司常法顾问-2025年8月12日至2026年8月11日",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


def test_full_chinese_date_wrong_end() -> None:
    """标题结束日期与实际不一致 → 报错。"""
    with pytest.raises(ValidationException, match="结束日期"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司常法顾问-2026年8月12日至2026年8月11日",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


def test_full_chinese_date_wrong_day() -> None:
    """年月正确但日期差一天 → 报错。"""
    with pytest.raises(ValidationException, match="结束日期"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司常法顾问-2026年8月12日至2027年8月12日",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


# ---------------------------------------------------------------------------
# 年度范围格式
# ---------------------------------------------------------------------------


def test_year_range_dash_correct() -> None:
    """2026-2027 年度，实际日期跨越 2026~2027 → 通过。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司2026-2027年度常法顾问合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_year_range_tilde_correct() -> None:
    """波浪线分隔的年份范围也能识别。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司2026～2027年度常法顾问合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_year_range_wrong_past() -> None:
    """年份范围是过去年度（2024-2025），但实际日期是 2026~2027 → 报错。"""
    with pytest.raises(ValidationException, match="年度范围"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司2024-2025年度常法顾问合同",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


def test_year_range_wrong_offset() -> None:
    """年份范围偏移一年（2025-2026），但实际是 2026~2027 → 报错。"""
    with pytest.raises(ValidationException, match="年度范围"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司2025-2026年度常法顾问合同",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


def test_year_range_cross_year_contract() -> None:
    """跨年合同（从 2025 年底到 2027 年初），标题 2025-2027 → 通过。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司2025-2027年度常法顾问合同",
        start_date=date(2025, 12, 1),
        end_date=date(2027, 1, 31),
    )


def test_year_range_swapped_order() -> None:
    """标题年份范围倒序（2027-2026），但实际日期 2026~2027 → 自动交换，通过。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司2027-2026年度常法顾问合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


# ---------------------------------------------------------------------------
# 短横线年份缩写 (26-27)
# ---------------------------------------------------------------------------


def test_short_year_range_correct() -> None:
    """两位年份缩写 26-27 正确解析为 2026-2027。"""
    validate_advisor_contract_title_dates(
        case_type="advisor",
        title="某某公司26-27年度常法顾问合同",
        start_date=date(2026, 8, 12),
        end_date=date(2027, 8, 11),
    )


def test_short_year_range_wrong() -> None:
    """两位年份缩写 24-25 与实际 2026~2027 不匹配 → 报错。"""
    with pytest.raises(ValidationException, match="年度范围"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="某某公司24-25年度常法顾问合同",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )


# ---------------------------------------------------------------------------
# 完整日期优先于年份范围
# ---------------------------------------------------------------------------


def test_both_full_date_and_year_range_full_date_wrong() -> None:
    """标题同时含完整日期和年份范围时，以完整日期为准（完整日期错 → 报错）。"""
    with pytest.raises(ValidationException, match="开始日期"):
        validate_advisor_contract_title_dates(
            case_type="advisor",
            title="2026-2027年度常法顾问-2025年8月12日至2026年8月11日",
            start_date=date(2026, 8, 12),
            end_date=date(2027, 8, 11),
        )
