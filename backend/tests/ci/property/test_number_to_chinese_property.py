"""Property-based tests for NumberPlaceholderService (number-to-Chinese)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

svc = NumberPlaceholderService()

# Chinese digit chars that can appear in integer parts
CHINESE_DIGITS = set("零壹贰叁肆伍陆柒捌玖")
CHINESE_UNITS = set("拾佰仟万亿")


# ---------------------------------------------------------------------------
# number_to_chinese
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(amount=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999999.99"), allow_nan=False, allow_infinity=False))
def test_number_to_chinese_positive_ends_with_yuan(amount: Decimal) -> None:
    """Positive amounts produce output ending with '元' (possibly followed by '整' or decimal)."""
    result = svc.number_to_chinese(amount)
    assert "元" in result, f"expected '元' in {result!r}"


@settings(max_examples=200, deadline=None)
@given(amount=st.one_of(st.none(), st.just(0), st.just("0"), st.just(Decimal("0"))))
def test_number_to_chinese_zero(amount: object) -> None:
    """Zero / falsy inputs produce either '零' or '零元整'."""
    result = svc.number_to_chinese(amount)
    # Decimal('0') and None/0 are falsy -> "零"; string '0' is truthy -> "零元整"
    assert "零" in result


@settings(max_examples=200, deadline=None)
@given(
    integer_part=st.integers(min_value=1, max_value=999999999),
)
def test_number_to_chinese_whole_amount_ends_with_yuanzheng(integer_part: int) -> None:
    """Whole amounts (no decimal) end with '元整'."""
    result = svc.number_to_chinese(Decimal(str(integer_part)))
    assert result.endswith("元整")


@settings(max_examples=200, deadline=None)
@given(amount=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999999.99"), allow_nan=False, allow_infinity=False))
def test_number_to_chinese_uses_valid_chars(amount: Decimal) -> None:
    """All characters in the output are from the valid Chinese money character set."""
    result = svc.number_to_chinese(amount)
    valid_chars = CHINESE_DIGITS | CHINESE_UNITS | {"元", "角", "分", "整"}
    for ch in result:
        assert ch in valid_chars, f"unexpected char {ch!r} in {result!r}"


# ---------------------------------------------------------------------------
# _convert_integer_part
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=0, max_value=999999999))
def test_convert_integer_part_no_consecutive_zeros(n: int) -> None:
    """Output never contains consecutive '零'."""
    result = svc._convert_integer_part(str(n))
    assert "零零" not in result


@settings(max_examples=200, deadline=None)
@given(n=st.just(0))
def test_convert_integer_part_zero(n: int) -> None:
    """'0' produces '零'."""
    result = svc._convert_integer_part("0")
    assert result == "零"


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=1, max_value=999999999))
def test_convert_integer_part_not_empty(n: int) -> None:
    """Positive integers produce non-empty output."""
    result = svc._convert_integer_part(str(n))
    assert len(result) > 0


# ---------------------------------------------------------------------------
# _convert_decimal_part
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    jiao=st.just(0),
    fen=st.just(0),
)
def test_convert_decimal_part_zero_zero_is_zheng(jiao: int, fen: int) -> None:
    """'00' produces '整'."""
    result = svc._convert_decimal_part("00")
    assert result == "整"


@settings(max_examples=200, deadline=None)
@given(
    jiao=st.integers(min_value=0, max_value=9),
    fen=st.integers(min_value=0, max_value=9),
)
def test_convert_decimal_part_max_two_units(jiao: int, fen: int) -> None:
    """Decimal part has at most two unit characters (角 and 分)."""
    assume(jiao + fen > 0)
    decimal_str = f"{jiao}{fen}"
    result = svc._convert_decimal_part(decimal_str)
    # "角" appears at most once, "分" appears at most once
    assert result.count("角") <= 1
    assert result.count("分") <= 1
    assert len(result) <= 4  # e.g., "玖角玖分"


@settings(max_examples=200, deadline=None)
@given(
    jiao=st.integers(min_value=1, max_value=9),
)
def test_convert_decimal_part_nonzero_jiao_has_jiao(jiao: int) -> None:
    """When jiao > 0, result contains '角'."""
    decimal_str = f"{jiao}0"
    result = svc._convert_decimal_part(decimal_str)
    assert "角" in result
