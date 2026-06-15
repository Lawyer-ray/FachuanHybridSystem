"""Property-based tests for apps.core.utils.validators.Validators."""

from __future__ import annotations

import string
from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.core.utils.validators import Validators
from apps.core.exceptions import ValidationException

# ---------------------------------------------------------------------------
# Module-level strategies
# ---------------------------------------------------------------------------

# Chinese mobile prefixes: 13x, 14x, 15x, 16x, 17x, 18x, 19x
_phone_prefix = st.sampled_from([f"1{d}" for d in "3456789"])
_phone_suffix = st.from_regex(r"\d{9}", fullmatch=True)

_valid_phone = st.tuples(_phone_prefix, _phone_suffix).map(lambda t: t[0] + t[1])

_valid_email_local = st.from_regex(r"[a-zA-Z0-9._%+-]{1,30}", fullmatch=True)
_valid_email_domain = st.from_regex(r"[a-zA-Z0-9-]{1,15}", fullmatch=True)
_valid_email_tld = st.from_regex(r"[a-zA-Z]{2,10}", fullmatch=True)
_valid_email = st.tuples(_valid_email_local, _valid_email_domain, _valid_email_tld).map(
    lambda t: f"{t[0]}@{t[1]}.{t[2]}"
)

# Unified social credit code: 2 org-type chars + 6 administrative area digits + 10 entity chars
_scc_org_chars = st.sampled_from(list("0123456789ABCDEFGHJKLMNPQRTUWXY"))
_scc_area_digits = st.from_regex(r"\d{6}", fullmatch=True)
_scc_entity_chars = st.sampled_from(list("0123456789ABCDEFGHJKLMNPQRTUWXY"))
_valid_social_credit_code = st.tuples(
    _scc_org_chars, _scc_org_chars, _scc_area_digits,
    _scc_entity_chars, _scc_entity_chars, _scc_entity_chars,
    _scc_entity_chars, _scc_entity_chars, _scc_entity_chars,
    _scc_entity_chars, _scc_entity_chars, _scc_entity_chars,
    _scc_entity_chars,
).map(lambda t: "".join(t))


# ===========================================================================
# validate_phone
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(phone=_valid_phone)
def test_validate_phone_valid_returns_stripped_string(phone: str) -> None:
    """A valid 11-digit phone returns a string equal to the stripped input."""
    result = Validators.validate_phone(phone)
    assert result == phone.strip()
    assert isinstance(result, str)


@settings(max_examples=200, deadline=None)
@given(phone=_valid_phone)
def test_validate_phone_idempotent(phone: str) -> None:
    """Validating twice returns the same result."""
    r1 = Validators.validate_phone(phone)
    r2 = Validators.validate_phone(r1)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(phone=_valid_phone)
def test_validate_phone_with_surrounding_whitespace(phone: str) -> None:
    """Surrounding whitespace is stripped from valid phone numbers."""
    padded = f"  {phone}  "
    result = Validators.validate_phone(padded)
    assert result == phone


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.sampled_from(["0", "2", "5", "6"]),
    suffix=st.from_regex(r"\d{9}", fullmatch=True),
)
def test_validate_phone_invalid_prefix_raises(prefix: str, suffix: str) -> None:
    """Phones not starting with 1[3-9] raise ValidationException."""
    phone = prefix + suffix
    try:
        Validators.validate_phone(phone)
        assert False, f"Expected ValidationException for {phone!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=1, max_value=20).filter(lambda v: v != 11))
def test_validate_phone_wrong_length_raises(n: int) -> None:
    """Phones not 11 digits raise ValidationException."""
    phone = "1" * n
    try:
        Validators.validate_phone(phone)
        assert False, f"Expected ValidationException for length {n}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_phone_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_phone(None) is None


@settings(max_examples=200, deadline=None)
@given(s=st.sampled_from(["", "   ", "\t\n"]))
def test_validate_phone_empty_or_whitespace_returns_none(s: str) -> None:
    """Empty or whitespace-only strings return None."""
    assert Validators.validate_phone(s) is None


@settings(max_examples=200, deadline=None)
@given(phone=_valid_phone, field=st.text(min_size=1, max_size=30))
def test_validate_phone_custom_field_name_in_error(phone: str, field: str) -> None:
    """Invalid phone with custom field_name propagates into the error dict."""
    bad = "000" + phone[3:]
    try:
        Validators.validate_phone(bad, field_name=field)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


# ===========================================================================
# validate_email
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(email=_valid_email)
def test_validate_email_output_always_lowercase(email: str) -> None:
    """Valid email result is always lowercase."""
    result = Validators.validate_email(email)
    assert result == result.lower()


@settings(max_examples=200, deadline=None)
@given(email=_valid_email)
def test_validate_email_idempotent(email: str) -> None:
    """Validating twice gives the same result."""
    r1 = Validators.validate_email(email)
    r2 = Validators.validate_email(r1)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_email_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_email(None) is None


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_email_empty_returns_none(dummy: None) -> None:
    """Empty string input returns None (falsy check before strip)."""
    assert Validators.validate_email("") is None


@settings(max_examples=200, deadline=None)
@given(s=st.sampled_from(["   ", "\t", "  \n  "]))
def test_validate_email_whitespace_only_raises(s: str) -> None:
    """Whitespace-only strings are truthy, get stripped to '', and fail the regex."""
    try:
        Validators.validate_email(s)
        assert False, f"Expected ValidationException for whitespace-only {s!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(bad=st.text(min_size=1, max_size=30).filter(lambda s: "@" not in s))
def test_validate_email_no_at_sign_raises(bad: str) -> None:
    """Strings without '@' are invalid emails."""
    try:
        Validators.validate_email(bad)
        assert False, f"Expected ValidationException for {bad!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.from_regex(r"[a-zA-Z]{1,10}", fullmatch=True),
    tld=st.from_regex(r"[a-zA-Z]{2,5}", fullmatch=True),
)
def test_validate_email_with_surrounding_whitespace(prefix: str, tld: str) -> None:
    """Surrounding whitespace is stripped and result is lowercase."""
    email = f"  {prefix}@example.{tld}  "
    result = Validators.validate_email(email)
    assert result == f"{prefix.lower()}@example.{tld.lower()}"


# ===========================================================================
# validate_social_credit_code
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(code=_valid_social_credit_code)
def test_validate_scc_output_always_uppercase(code: str) -> None:
    """Result is always uppercase."""
    result = Validators.validate_social_credit_code(code)
    assert result == result.upper()


@settings(max_examples=200, deadline=None)
@given(code=_valid_social_credit_code)
def test_validate_scc_idempotent(code: str) -> None:
    """Validating twice gives the same result."""
    r1 = Validators.validate_social_credit_code(code)
    r2 = Validators.validate_social_credit_code(r1)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(code=_valid_social_credit_code)
def test_validate_scc_valid_length_18(code: str) -> None:
    """Result is always 18 characters long."""
    result = Validators.validate_social_credit_code(code)
    assert len(result) == 18


@settings(max_examples=200, deadline=None)
@given(code=_valid_social_credit_code)
def test_validate_scc_result_matches_pattern(code: str) -> None:
    """Result matches the SOCIAL_CREDIT_CODE_PATTERN."""
    result = Validators.validate_social_credit_code(code)
    assert Validators.SOCIAL_CREDIT_CODE_PATTERN.match(result)


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_scc_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_social_credit_code(None) is None


@settings(max_examples=200, deadline=None)
@given(
    bad=st.text(min_size=18, max_size=18).filter(
        lambda s: not Validators.SOCIAL_CREDIT_CODE_PATTERN.match(s.upper())
    ),
)
def test_validate_scc_invalid_raises(bad: str) -> None:
    """18-char strings that don't match the pattern raise ValidationException."""
    try:
        Validators.validate_social_credit_code(bad)
        assert False, f"Expected ValidationException for {bad!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=1, max_value=30).filter(lambda v: v != 18))
def test_validate_scc_wrong_length_raises(n: int) -> None:
    """Codes not 18 characters long raise ValidationException."""
    code = "A" * n
    try:
        Validators.validate_social_credit_code(code)
        assert False, f"Expected ValidationException for length {n}"
    except ValidationException:
        pass


# ===========================================================================
# validate_decimal
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(value=st.decimals(min_value=Decimal("0"), max_value=Decimal("999999999.99"), places=2))
def test_validate_decimal_returns_decimal(value: Decimal) -> None:
    """Valid decimal values within default bounds return a Decimal."""
    result = Validators.validate_decimal(value, "amount", max_digits=14, decimal_places=2)
    assert isinstance(result, Decimal)


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_decimal_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_decimal(None, "amount") is None


@settings(max_examples=200, deadline=None)
@given(
    int_part=st.integers(min_value=0, max_value=999),
    dec_part=st.integers(min_value=0, max_value=99),
)
def test_validate_decimal_within_bounds(int_part: int, dec_part: int) -> None:
    """A value with at most 3+2=5 integer digits and 2 decimal places is valid for max_digits=5, decimal_places=2."""
    value = f"{int_part}.{dec_part:02d}"
    result = Validators.validate_decimal(value, "amount", max_digits=5, decimal_places=2)
    assert result is not None
    assert isinstance(result, Decimal)


@settings(max_examples=200, deadline=None)
@given(
    int_digits=st.integers(min_value=4, max_value=20),
)
def test_validate_decimal_integer_overflow_raises(int_digits: int) -> None:
    """When integer part + decimal_places > max_digits, raises ValidationException."""
    value = "9" * int_digits + ".00"
    try:
        Validators.validate_decimal(value, "amount", max_digits=5, decimal_places=2)
        assert False, f"Expected ValidationException for {value!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    extra_dec=st.integers(min_value=1, max_value=10),
)
def test_validate_decimal_too_many_decimal_places_raises(extra_dec: int) -> None:
    """When decimal digits > decimal_places, raises ValidationException."""
    value = "1." + "1" * (2 + extra_dec)
    try:
        Validators.validate_decimal(value, "amount", max_digits=14, decimal_places=2)
        assert False, f"Expected ValidationException for {value!r}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(bad=st.text(min_size=1, max_size=20).filter(
    lambda s: not s.strip().replace(".", "", 1).replace("-", "", 1).isdigit()
))
def test_validate_decimal_non_numeric_raises(bad: str) -> None:
    """Non-numeric strings raise ValidationException."""
    try:
        Validators.validate_decimal(bad, "amount")
        # If it succeeds, it must be a valid Decimal after stripping
        from decimal import Decimal
        Decimal(bad.strip())
    except (ValidationException, Exception):
        pass


# ===========================================================================
# validate_length
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(
    s=st.text(min_size=1, max_size=50),
)
def test_validate_length_pass_through_within_bounds(s: str) -> None:
    """Strings within min/max length pass through unchanged."""
    result = Validators.validate_length(s, "field", min_length=0, max_length=100)
    assert result == s


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_length_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_length(None, "field", min_length=1, max_length=10) is None


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(""))
def test_validate_length_empty_string_returns_none(dummy: str) -> None:
    """Empty string returns None."""
    assert Validators.validate_length("", "field", min_length=1, max_length=10) is None


@settings(max_examples=200, deadline=None)
@given(s=st.text(min_size=1, max_size=50))
def test_validate_length_below_min_raises(s: str) -> None:
    """Strings shorter than min_length raise ValidationException."""
    min_len = len(s) + 1
    try:
        Validators.validate_length(s, "field", min_length=min_len)
        assert False, f"Expected ValidationException for len({len(s)}) < {min_len}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(s=st.text(min_size=1, max_size=50))
def test_validate_length_above_max_raises(s: str) -> None:
    """Strings longer than max_length raise ValidationException."""
    max_len = len(s) - 1
    assume(max_len >= 0)
    try:
        Validators.validate_length(s, "field", max_length=max_len)
        assert False, f"Expected ValidationException for len({len(s)}) > {max_len}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    s=st.text(min_size=1, max_size=50),
)
def test_validate_length_exact_boundary_passes(s: str) -> None:
    """A string of exactly min_length or max_length passes."""
    n = len(s)
    result = Validators.validate_length(s, "field", min_length=n, max_length=n)
    assert result == s


# ===========================================================================
# validate_range
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
def test_validate_range_within_bounds_passes(value: float) -> None:
    """Values within [-1e6, 1e6] pass with matching bounds."""
    result = Validators.validate_range(value, "field", min_value=-1e6, max_value=1e6)
    assert result == value


@settings(max_examples=200, deadline=None)
@given(dummy=st.just(None))
def test_validate_range_none_returns_none(dummy: None) -> None:
    """None input returns None."""
    assert Validators.validate_range(None, "field", min_value=0, max_value=100) is None


@settings(max_examples=200, deadline=None)
@given(
    bound=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    offset=st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_validate_range_below_min_raises(bound: float, offset: float) -> None:
    """Values below min_value raise ValidationException."""
    value = bound - offset
    try:
        Validators.validate_range(value, "field", min_value=bound)
        assert False, f"Expected ValidationException for {value} < {bound}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    bound=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    offset=st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_validate_range_above_max_raises(bound: float, offset: float) -> None:
    """Values above max_value raise ValidationException."""
    value = bound + offset
    try:
        Validators.validate_range(value, "field", max_value=bound)
        assert False, f"Expected ValidationException for {value} > {bound}"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(value=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_validate_range_only_min(value: float) -> None:
    """With only min_value, values >= min pass and values < min raise."""
    if value >= -1e9:
        result = Validators.validate_range(value, "field", min_value=-1e9)
        assert result == value


@settings(max_examples=200, deadline=None)
@given(value=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_validate_range_only_max(value: float) -> None:
    """With only max_value, values <= max pass and values > max raise."""
    if value <= 1e9:
        result = Validators.validate_range(value, "field", max_value=1e9)
        assert result == value


@settings(max_examples=200, deadline=None)
@given(value=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_validate_range_no_bounds_passes(value: float) -> None:
    """With no bounds specified, all values pass through."""
    result = Validators.validate_range(value, "field")
    assert result == value


# ===========================================================================
# Error paths: ValidationException carries correct field_name
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(field=st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + string.digits + "_"))
def test_validate_phone_error_contains_field_name(field: str) -> None:
    """Invalid phone raises ValidationException with the given field_name in errors dict."""
    try:
        Validators.validate_phone("abc", field_name=field)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


@settings(max_examples=200, deadline=None)
@given(field=st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + string.digits + "_"))
def test_validate_email_error_contains_field_name(field: str) -> None:
    """Invalid email raises ValidationException with the given field_name in errors dict."""
    try:
        Validators.validate_email("not-an-email", field_name=field)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


@settings(max_examples=200, deadline=None)
@given(field=st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + string.digits + "_"))
def test_validate_length_error_contains_field_name(field: str) -> None:
    """Length violation raises ValidationException with the given field_name in errors dict."""
    try:
        Validators.validate_length("x", field, min_length=10)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


@settings(max_examples=200, deadline=None)
@given(field=st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + string.digits + "_"))
def test_validate_range_error_contains_field_name(field: str) -> None:
    """Range violation raises ValidationException with the given field_name in errors dict."""
    try:
        Validators.validate_range(-999.0, field, min_value=0)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


@settings(max_examples=200, deadline=None)
@given(field=st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + string.digits + "_"))
def test_validate_decimal_error_contains_field_name(field: str) -> None:
    """Decimal violation raises ValidationException with the given field_name in errors dict."""
    try:
        Validators.validate_decimal("abc", field)
        assert False, "Expected ValidationException"
    except ValidationException as exc:
        assert field in exc.errors


# ===========================================================================
# No-crash invariants: arbitrary input should not crash (only raise or return)
# ===========================================================================


@settings(max_examples=200, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=50), st.integers(), st.floats(allow_nan=True, allow_infinity=True)))
def test_validate_decimal_no_crash(value: object) -> None:
    """validate_decimal either returns a value or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_decimal(value, "field")
        assert result is None or isinstance(result, Decimal)
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    value=st.one_of(st.none(), st.integers(), st.floats(allow_nan=True, allow_infinity=True)),
    min_v=st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
    max_v=st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
)
def test_validate_range_no_crash(value: object, min_v: float | None, max_v: float | None) -> None:
    """validate_range either returns a value or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_range(value, "field", min_value=min_v, max_value=max_v)
        assert result is value or result is None
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=100)))
def test_validate_length_no_crash(value: str | None) -> None:
    """validate_length either returns a value or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_length(value, "field", min_length=0, max_length=50)
        assert result is None or isinstance(result, str)
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=100)))
def test_validate_phone_no_crash(value: str | None) -> None:
    """validate_phone either returns None/str or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_phone(value)
        assert result is None or isinstance(result, str)
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=100)))
def test_validate_email_no_crash(value: str | None) -> None:
    """validate_email either returns None/str or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_email(value)
        assert result is None or isinstance(result, str)
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=100)))
def test_validate_scc_no_crash(value: str | None) -> None:
    """validate_social_credit_code either returns None/str or raises ValidationException -- never crashes."""
    try:
        result = Validators.validate_social_credit_code(value)
        assert result is None or isinstance(result, str)
    except ValidationException:
        pass
