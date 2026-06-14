"""Property-based tests for IdCardUtils."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.utils.id_card_utils import IdCardUtils


def _valid_18_digit_id_numbers() -> st.SearchStrategy[str]:
    """Generate structurally valid 18-digit ID card numbers.

    An 18-digit ID is structured as:
      6-digit region + 8-digit birthdate (YYYYMMDD) + 3-digit sequence + 1 check digit
    = 18 digits total (17 + 1 checksum).
    """
    from apps.core.utils.id_card_utils import ID_CARD_CHECK_CODES, ID_CARD_WEIGHTS

    # 6-digit region code: province (2) + city/area (4)
    region = st.integers(min_value=110000, max_value=659999).map(lambda x: f"{x:06d}")
    # Year between 1950-2005 to ensure valid dates
    year = st.integers(min_value=1950, max_value=2005)
    month = st.integers(min_value=1, max_value=12)
    day = st.integers(min_value=1, max_value=28)  # safe upper bound
    seq = st.integers(min_value=0, max_value=999)

    def _build(r: str, y: int, m: int, d: int, s: int) -> str:
        # 6-digit region + 8-digit date + 3-digit sequence = 17 digits
        prefix17 = f"{r}{y:04d}{m:02d}{d:02d}{s:03d}"
        assert len(prefix17) == 17, f"prefix17 length {len(prefix17)}: {prefix17!r}"
        total = sum(int(prefix17[i]) * ID_CARD_WEIGHTS[i] for i in range(17))
        return prefix17 + ID_CARD_CHECK_CODES[total % 11]

    return st.builds(_build, region, year, month, day, seq)


# ---- extract_birth_date ----


@settings(max_examples=200, deadline=None)
@given(_valid_18_digit_id_numbers())
def test_extract_birth_date_18_digit_format(id_number: str) -> None:
    result = IdCardUtils.extract_birth_date(id_number)
    assert result is not None, f"extract_birth_date returned None for {id_number}"
    # Should match "YYYY年MM月DD日"
    assert result.endswith("日"), f"Unexpected format: {result}"
    parts = result.replace("年", "-").replace("月", "-").replace("日", "").split("-")
    assert len(parts) == 3, f"Unexpected date parts: {parts}"
    assert len(parts[0]) == 4 and parts[0].isdigit()
    # month and day from the ID number (indices 10:12 and 12:14)
    expected_month = id_number[10:12]
    expected_day = id_number[12:14]
    assert parts[1] == expected_month, f"Month mismatch: {parts[1]} vs {expected_month}"
    assert parts[2] == expected_day, f"Day mismatch: {parts[2]} vs {expected_day}"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=13))
def test_extract_birth_date_short_input_returns_none(text: str) -> None:
    assert IdCardUtils.extract_birth_date(text) is None


# ---- extract_gender ----


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=13))
def test_extract_gender_short_input_returns_none(text: str) -> None:
    assert IdCardUtils.extract_gender(text) is None


@settings(max_examples=200, deadline=None)
@given(_valid_18_digit_id_numbers())
def test_extract_gender_18_digit_valid(id_number: str) -> None:
    result = IdCardUtils.extract_gender(id_number)
    assert result in ("男", "女"), f"Unexpected gender: {result!r}"
    # 17th digit (index 16) odd -> male, even -> female
    digit_17 = int(id_number[16])
    expected = "男" if digit_17 % 2 == 1 else "女"
    assert result == expected


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=5), st.text(max_size=5))
def test_extract_gender_output_in_expected_set(prefix: str, suffix: str) -> None:
    """For arbitrary input, output is always one of {male, female, None}."""
    # Ensure input is at least 14 chars so it reaches the digit parsing
    text = prefix + "0" * max(0, 14 - len(prefix) - len(suffix)) + suffix
    result = IdCardUtils.extract_gender(text)
    assert result in ("男", "女", None)


# ---- validate_id_card ----


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=100))
def test_validate_id_card_always_has_required_keys(text: str) -> None:
    result = IdCardUtils.validate_id_card(text)
    assert "valid" in result, f"Missing 'valid' key"
    assert "message" in result, f"Missing 'message' key"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=100))
def test_validate_id_card_empty_string_invalid(text: str) -> None:
    # Only test truly empty-ish inputs
    stripped = text.strip()
    if not stripped:
        result = IdCardUtils.validate_id_card(stripped)
        assert result["valid"] is False


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=16, max_size=16).filter(lambda s: s.strip() != ""))
def test_validate_id_card_16_digit_invalid(text: str) -> None:
    result = IdCardUtils.validate_id_card(text.strip())
    assert result["valid"] is False


@settings(max_examples=200, deadline=None)
@given(_valid_18_digit_id_numbers())
def test_validate_id_card_known_valid_numbers(id_number: str) -> None:
    result = IdCardUtils.validate_id_card(id_number)
    assert result["valid"] is True, f"Expected valid for {id_number}, got: {result}"


@settings(max_examples=200, deadline=None)
@given(st.just("110101199003071234"))
def test_validate_id_card_known_invalid_checksum(test_id: str) -> None:
    """Known invalid 18-digit ID (bad checksum) should be rejected."""
    result = IdCardUtils.validate_id_card(test_id)
    assert result["valid"] is False
