"""Property-based tests for reminder parser and validators."""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.exceptions import ValidationException
from apps.reminders.models import ReminderType
from apps.reminders.services.reminder_parser_service import (
    DEFAULT_REMINDER_TYPE,
    REMINDER_TYPE_LABELS,
    _infer_reminder_type,
    _parse_date,
)
from apps.reminders.services.validators import normalize_content, normalize_reminder_type


# ---- _parse_date ----


@settings(max_examples=200, deadline=None)
@given(st.dates(min_value=datetime(1900, 1, 1).date(), max_value=datetime(2099, 12, 31).date()))
def test_parse_date_valid_dates(dt) -> None:
    """Well-formatted date strings should parse back to datetime."""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        text = dt.strftime(fmt)
        result = _parse_date(text)
        assert result is not None, f"_parse_date returned None for {text!r}"
        assert result.year == dt.year
        assert result.month == dt.month
        assert result.day == dt.day


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=64).filter(lambda s: not any(c.isdigit() for c in s) or len(s.strip()) == 0))
def test_parse_date_invalid_returns_none(text: str) -> None:
    assert _parse_date(text) is None


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_parse_date_empty_returns_none(text: str) -> None:
    assert _parse_date(text) is None


# ---- _infer_reminder_type ----


_KNOWN_TYPES = set(REMINDER_TYPE_LABELS.keys())


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=512))
def test_infer_reminder_type_in_known_set(text: str) -> None:
    result = _infer_reminder_type(text)
    assert result in _KNOWN_TYPES, f"Unknown reminder type: {result!r}"


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_infer_reminder_type_empty_returns_default(text: str) -> None:
    assert _infer_reminder_type(text) == DEFAULT_REMINDER_TYPE


# ---- normalize_reminder_type ----


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(list(ReminderType.values)))
def test_normalize_reminder_type_valid_values(value: str) -> None:
    result = normalize_reminder_type(value)
    assert result in ReminderType.values


@settings(max_examples=200, deadline=None)
@given(
    st.text(max_size=64).filter(
        lambda s: s.strip() not in ReminderType.values
    )
)
def test_normalize_reminder_type_invalid_raises(text: str) -> None:
    """Invalid reminder types should raise ValidationException."""
    import pytest

    with pytest.raises(ValidationException):
        normalize_reminder_type(text)


# ---- normalize_content ----


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=255).filter(lambda s: len(s.strip()) > 0))
def test_normalize_content_no_leading_trailing_whitespace(text: str) -> None:
    result = normalize_content(text)
    assert result == result.strip(), f"Content has leading/trailing whitespace: {result!r}"


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=255).filter(lambda s: len(s.strip()) > 0))
def test_normalize_content_max_length(text: str) -> None:
    result = normalize_content(text)
    assert len(result) <= 255, f"Content length {len(result)} > 255"


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_normalize_content_empty_raises(text: str) -> None:
    import pytest

    with pytest.raises(ValidationException):
        normalize_content(text)


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=256, max_size=1024).filter(lambda s: len(s.strip()) > 255))
def test_normalize_content_too_long_raises(text: str) -> None:
    import pytest

    with pytest.raises(ValidationException):
        normalize_content(text)
