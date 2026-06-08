"""提醒验证器和解析器单元测试。"""
from __future__ import annotations

from datetime import datetime

import pytest
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.reminders.services.reminder_parser_service import (
    ParsedReminder,
    _extract_sentence,
    _extract_time_near_date,
    _generate_content,
    _infer_reminder_type,
    _parse_date,
    parse_reminders_from_text,
)
from apps.reminders.services.validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_target_id,
    normalize_reminder_type,
    validate_binding_exclusive,
    validate_positive_id,
)


# ── normalize_target_id ────────────────────────────────────────────────────

def test_normalize_target_id_none() -> None:
    """None 返回 None。"""
    assert normalize_target_id(None, field_name="id") is None


def test_normalize_target_id_valid() -> None:
    """正整数正常返回。"""
    assert normalize_target_id(42, field_name="id") == 42


def test_normalize_target_id_negative() -> None:
    """负整数抛出异常。"""
    with pytest.raises(ValidationException):
        normalize_target_id(-1, field_name="id")


def test_normalize_target_id_zero() -> None:
    """0 抛出异常。"""
    with pytest.raises(ValidationException):
        normalize_target_id(0, field_name="id")


def test_normalize_target_id_bool() -> None:
    """布尔值抛出异常。"""
    with pytest.raises(ValidationException):
        normalize_target_id(True, field_name="id")


# ── validate_positive_id ───────────────────────────────────────────────────

def test_validate_positive_id_valid() -> None:
    """正整数不抛出异常。"""
    validate_positive_id(1, field_name="id")


def test_validate_positive_id_zero() -> None:
    """0 抛出异常。"""
    with pytest.raises(ValidationException):
        validate_positive_id(0, field_name="id")


def test_validate_positive_id_negative() -> None:
    """负数抛出异常。"""
    with pytest.raises(ValidationException):
        validate_positive_id(-5, field_name="id")


def test_validate_positive_id_bool() -> None:
    """布尔值抛出异常。"""
    with pytest.raises(ValidationException):
        validate_positive_id(True, field_name="id")


# ── validate_binding_exclusive ─────────────────────────────────────────────

def test_binding_exclusive_none_all() -> None:
    """全部 None 不抛出异常。"""
    validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)


def test_binding_exclusive_one_bound() -> None:
    """绑定一个不抛出异常。"""
    validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)


def test_binding_exclusive_two_bound() -> None:
    """绑定两个抛出异常。"""
    with pytest.raises(ValidationException, match="最多只能绑定一个"):
        validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)


def test_binding_exclusive_three_bound() -> None:
    """绑定三个抛出异常。"""
    with pytest.raises(ValidationException):
        validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=3)


# ── normalize_reminder_type ────────────────────────────────────────────────

def test_normalize_reminder_type_valid() -> None:
    """有效类型正常返回。"""
    result = normalize_reminder_type("hearing")
    assert result == "hearing"


def test_normalize_reminder_type_empty() -> None:
    """空字符串抛出异常。"""
    with pytest.raises(ValidationException, match="不能为空"):
        normalize_reminder_type("")


def test_normalize_reminder_type_invalid() -> None:
    """无效类型抛出异常。"""
    with pytest.raises(ValidationException, match="无效"):
        normalize_reminder_type("nonexistent_type")


# ── normalize_content ──────────────────────────────────────────────────────

def test_normalize_content_valid() -> None:
    """有效内容正常返回。"""
    assert normalize_content("开庭通知") == "开庭通知"


def test_normalize_content_strips_whitespace() -> None:
    """去除首尾空白。"""
    assert normalize_content("  开庭通知  ") == "开庭通知"


def test_normalize_content_empty() -> None:
    """空字符串抛出异常。"""
    with pytest.raises(ValidationException, match="不能为空"):
        normalize_content("")


def test_normalize_content_too_long() -> None:
    """超过 255 字符抛出异常。"""
    with pytest.raises(ValidationException, match="不能超过"):
        normalize_content("a" * 256)


# ── normalize_due_at ───────────────────────────────────────────────────────

def test_normalize_due_at_naive_makes_aware() -> None:
    """naive datetime 被转为 aware。"""
    naive = datetime(2024, 6, 15, 10, 0, 0)
    result = normalize_due_at(naive)
    assert timezone.is_aware(result)


def test_normalize_due_at_aware_unchanged() -> None:
    """aware datetime 不变。"""
    aware = timezone.now()
    result = normalize_due_at(aware)
    assert result == aware


# ── normalize_metadata ─────────────────────────────────────────────────────

def test_normalize_metadata_none() -> None:
    """None 返回空字典。"""
    assert normalize_metadata(None) == {}


def test_normalize_metadata_valid_dict() -> None:
    """有效字典正常返回。"""
    data = {"key": "value", "num": 42}
    assert normalize_metadata(data) == data


def test_normalize_metadata_not_dict() -> None:
    """非字典抛出异常。"""
    with pytest.raises(ValidationException, match="JSON 对象"):
        normalize_metadata("not a dict")


def test_normalize_metadata_non_serializable() -> None:
    """不可序列化的值抛出异常。"""
    with pytest.raises(ValidationException, match="不可序列化"):
        normalize_metadata({"key": object()})


# ── _infer_reminder_type ───────────────────────────────────────────────────

def test_infer_type_hearing() -> None:
    """开庭关键词推断为 hearing。"""
    assert _infer_reminder_type("2024年6月15日开庭") == "hearing"


def test_infer_type_evidence_deadline() -> None:
    """举证期限关键词推断。"""
    assert _infer_reminder_type("请在举证期限内提交") == "evidence_deadline"


def test_infer_type_appeal_deadline() -> None:
    """上诉期限关键词推断。"""
    assert _infer_reminder_type("上诉期限即将届满") == "appeal_deadline"


def test_infer_type_payment_deadline() -> None:
    """缴费期限关键词推断。"""
    assert _infer_reminder_type("缴费期限2024年6月") == "payment_deadline"


def test_infer_type_statute_limitations() -> None:
    """诉讼时效关键词推断。"""
    assert _infer_reminder_type("诉讼时效将届满") == "statute_limitations"


def test_infer_type_default() -> None:
    """无关键词默认 other。"""
    assert _infer_reminder_type("普通文本") == "other"


def test_infer_type_preservation() -> None:
    """保全到期关键词推断。"""
    assert _infer_reminder_type("保全到期2024年12月") == "asset_preservation_expires"


def test_infer_type_submission() -> None:
    """补正期限关键词推断。"""
    assert _infer_reminder_type("补正期限") == "submission_deadline"


# ── _parse_date ────────────────────────────────────────────────────────────

def test_parse_date_dash_format() -> None:
    """YYYY-MM-DD 格式。"""
    result = _parse_date("2024-06-15")
    assert result is not None
    assert result.year == 2024
    assert result.month == 6
    assert result.day == 15


def test_parse_date_slash_format() -> None:
    """YYYY/MM/DD 格式。"""
    result = _parse_date("2024/06/15")
    assert result is not None
    assert result.month == 6


def test_parse_date_dot_format() -> None:
    """YYYY.MM.DD 格式。"""
    result = _parse_date("2024.06.15")
    assert result is not None


def test_parse_date_chinese_format() -> None:
    """YYYY年MM月DD日 格式。"""
    result = _parse_date("2024年6月15日")
    assert result is not None
    assert result.day == 15


def test_parse_date_invalid() -> None:
    """无效日期返回 None。"""
    assert _parse_date("invalid") is None


def test_parse_date_empty() -> None:
    """空字符串返回 None。"""
    assert _parse_date("") is None


# ── _extract_time_near_date ────────────────────────────────────────────────

def test_extract_time_pm() -> None:
    """下午时间解析。"""
    text = "2024-06-15下午3点开庭"
    result = _extract_time_near_date(text, 10)
    assert result is not None
    assert result[0] == 15
    assert result[1] == 0


def test_extract_time_half() -> None:
    """半点解析。"""
    text = "2024-06-15下午3点半"
    result = _extract_time_near_date(text, 10)
    assert result is not None
    assert result[0] == 15
    assert result[1] == 30


def test_extract_time_am() -> None:
    """上午时间解析。"""
    text = "2024-06-15上午9点"
    result = _extract_time_near_date(text, 10)
    assert result is not None
    assert result[0] == 9


def test_extract_time_no_time() -> None:
    """日期后无时间信息返回 None。"""
    text = "2024-06-15开庭"
    result = _extract_time_near_date(text, 10)
    assert result is None


# ── parse_reminders_from_text ──────────────────────────────────────────────

def test_parse_reminders_basic() -> None:
    """基本提醒解析。"""
    text = "2024年6月15日下午3点开庭"
    results = parse_reminders_from_text(text)
    assert len(results) >= 1
    assert results[0].reminder_type == "hearing"


def test_parse_reminders_empty_text() -> None:
    """空文本返回空列表。"""
    assert parse_reminders_from_text("") == []
    assert parse_reminders_from_text("   ") == []
    assert parse_reminders_from_text(None) == []


def test_parse_reminders_no_date() -> None:
    """无日期返回空列表。"""
    assert parse_reminders_from_text("今天开庭") == []


def test_parse_reminders_multiple_dates() -> None:
    """多个日期解析多条。"""
    text = "2024年6月15日开庭，2024年7月1日举证期限"
    results = parse_reminders_from_text(text)
    assert len(results) >= 2


def test_parse_reminders_dedup_same_date() -> None:
    """相同日期去重。"""
    text = "2024年6月15日开庭，2024年6月15日举证"
    results = parse_reminders_from_text(text)
    assert len(results) == 1


# ── _extract_sentence ──────────────────────────────────────────────────────

def test_extract_sentence_basic() -> None:
    """基本句子提取。"""
    text = "2024年6月15日开庭，请准时到庭。"
    result = _extract_sentence(text, 0, 10)
    assert "开庭" in result


# ── _generate_content ──────────────────────────────────────────────────────

def test_generate_content_short() -> None:
    """短句子不截断。"""
    result = _generate_content("开庭通知", "开庭", datetime(2024, 6, 15))
    assert result == "开庭：开庭通知"


def test_generate_content_long_truncated() -> None:
    """长句子截断。"""
    sentence = "a" * 100
    result = _generate_content(sentence, "开庭", datetime(2024, 6, 15))
    assert len(result) <= 100
    assert "..." in result or "…" in result
