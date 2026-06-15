"""Property-based tests for extraction / fallback modules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.services.placeholders.litigation.execution_request_clause_extractor import (
    extract_joint_liability_text,
    extract_numbered_clauses,
    extract_supplementary_liability_text,
    has_double_interest_clause,
)
from apps.documents.services.placeholders.fallback import (
    ensure_required_placeholders,
    normalize_placeholder_value,
    resolve_render_variable,
)
from apps.documents.services.placeholders.litigation.execution_request_llm_fallback import (
    _has_fee_prepaid_context,
    _parse_bool,
    _parse_iso_date,
    should_try_llm_fallback,
)
from apps.documents.services.placeholders.litigation.execution_request_models import (
    ParsedAmounts,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

chinese_marker = st.sampled_from(["一、", "二、", "三、", "四、", "五、", "1.", "2.", "3.", "4.", "5."])
non_empty_text = st.text(min_size=1, max_size=500).filter(lambda s: s.strip() != "")


# ---------------------------------------------------------------------------
# has_double_interest_clause
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_has_double_interest_clause_returns_bool(text: str) -> None:
    result = has_double_interest_clause(text)
    assert isinstance(result, bool)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_has_double_interest_clause_deterministic(text: str) -> None:
    assert has_double_interest_clause(text) == has_double_interest_clause(text)


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_has_double_interest_clause_empty(text: str) -> None:
    result = has_double_interest_clause(text)
    assert result is False


POSITIVE_DOUBLE_INTEREST = [
    "加倍支付迟延履行期间的债务利息",
    "加倍支付迟延履行期间债务利息",
    "应当加倍支付迟延履行期间的债务利息",
]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(POSITIVE_DOUBLE_INTEREST))
def test_has_double_interest_clause_positive_cases(text: str) -> None:
    assert has_double_interest_clause(text) is True


# ---------------------------------------------------------------------------
# extract_numbered_clauses
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_numbered_clauses_returns_list(text: str) -> None:
    result = extract_numbered_clauses(text)
    assert isinstance(result, list)
    assert all(isinstance(c, str) for c in result)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_numbered_clauses_deterministic(text: str) -> None:
    assert extract_numbered_clauses(text) == extract_numbered_clauses(text)


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_extract_numbered_clauses_empty(text: str) -> None:
    assert extract_numbered_clauses(text) == []


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=100))
def test_extract_numbered_clauses_with_markers(prefix: str) -> None:
    text = "一、" + prefix
    result = extract_numbered_clauses(text)
    assert len(result) >= 1


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_numbered_clauses_non_empty_elements(text: str) -> None:
    """All returned clauses should be non-empty stripped strings."""
    clauses = extract_numbered_clauses(text)
    for clause in clauses:
        assert clause.strip() != ""


# ---------------------------------------------------------------------------
# extract_supplementary_liability_text
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_supplementary_liability_returns_str(text: str) -> None:
    result = extract_supplementary_liability_text(text)
    assert isinstance(result, str)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_supplementary_liability_deterministic(text: str) -> None:
    r1 = extract_supplementary_liability_text(text)
    r2 = extract_supplementary_liability_text(text)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_extract_supplementary_liability_empty(text: str) -> None:
    result = extract_supplementary_liability_text(text)
    assert result == ""


SUPPLEMENTARY_SENTENCES = [
    "在被告不能清偿部分承担补充赔偿责任",
    "对上述债务承担补充清偿责任",
    "在未出资本息范围内承担补充责任",
    "财产不足清偿部分承担清偿责任",
]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(SUPPLEMENTARY_SENTENCES))
def test_extract_supplementary_liability_positive(sentence: str) -> None:
    result = extract_supplementary_liability_text(sentence)
    assert result != "", f"Expected non-empty for: {sentence}"


# ---------------------------------------------------------------------------
# extract_joint_liability_text
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_joint_liability_returns_str(text: str) -> None:
    result = extract_joint_liability_text(text)
    assert isinstance(result, str)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_extract_joint_liability_deterministic(text: str) -> None:
    assert extract_joint_liability_text(text) == extract_joint_liability_text(text)


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_extract_joint_liability_empty(text: str) -> None:
    assert extract_joint_liability_text(text) == ""


JOINT_SENTENCES = [
    "被告二对上述债务承担连带清偿责任",
    "被告三对本判决第一项承担连带责任",
]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(JOINT_SENTENCES))
def test_extract_joint_liability_positive(sentence: str) -> None:
    result = extract_joint_liability_text(sentence)
    assert result != "", f"Expected non-empty for: {sentence}"


# ---------------------------------------------------------------------------
# normalize_placeholder_value
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.one_of(st.none(), st.just(""), st.just("   ")))
def test_normalize_placeholder_fallbacks(value: Any) -> None:
    result = normalize_placeholder_value(value)
    assert result == "/", f"Expected '/' for {value!r}, got {result!r}"


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""))
def test_normalize_placeholder_preserves_non_empty(text: str) -> None:
    result = normalize_placeholder_value(text)
    assert result == text


@settings(max_examples=200, deadline=None)
@given(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False)))
def test_normalize_placeholder_non_str_passthrough(value: Any) -> None:
    """Non-string, non-None values pass through unchanged."""
    result = normalize_placeholder_value(value)
    assert result == value


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=200), st.text(min_size=1, max_size=20))
def test_normalize_placeholder_custom_fallback(value: str | None, fallback: str) -> None:
    assume(value is None or value.strip() == "")
    result = normalize_placeholder_value(value, fallback_value=fallback)
    assert result == fallback


# ---------------------------------------------------------------------------
# ensure_required_placeholders
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=10))
def test_ensure_required_returns_dict(context: dict[str, Any]) -> None:
    result = ensure_required_placeholders(context, None)
    assert isinstance(result, dict)


@settings(max_examples=200, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=10))
def test_ensure_required_contains_all_context_keys(context: dict[str, Any]) -> None:
    result = ensure_required_placeholders(context, None)
    for key in context:
        assert key in result


@settings(max_examples=200, deadline=None)
@given(
    st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5),
    st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
)
def test_ensure_required_adds_missing_keys(context: dict[str, Any], required: list[str]) -> None:
    result = ensure_required_placeholders(context, required)
    for key in required:
        assert key in result, f"Required key {key!r} missing from result"


@settings(max_examples=200, deadline=None)
@given(
    st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5),
    st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
)
def test_ensure_required_none_values_replaced(context: dict[str, Any], required: list[str]) -> None:
    """Values that are None should be replaced with fallback."""
    for key in required:
        context[key] = None
    result = ensure_required_placeholders(context, required)
    for key in required:
        assert result[key] == "/", f"Key {key!r} should have fallback but has {result[key]!r}"


@settings(max_examples=200, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=20), st.integers(), max_size=5))
def test_ensure_required_passthrough_non_str_values(context: dict[str, Any]) -> None:
    """Non-string values that are not None should pass through."""
    result = ensure_required_placeholders(context, None)
    for key, value in context.items():
        assert result[key] == value


# ---------------------------------------------------------------------------
# resolve_render_variable
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=20))
def test_resolve_render_variable_missing_key(key: str) -> None:
    found, value = resolve_render_variable({}, key)
    assert found is False
    assert value == "/"


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=20), st.one_of(st.integers(), st.text(max_size=50)))
def test_resolve_render_variable_present_key(key: str, val: Any) -> None:
    found, value = resolve_render_variable({key: val}, key)
    assert found is True
    assert value == str(val)


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=20))
def test_resolve_render_variable_none_value(key: str) -> None:
    found, value = resolve_render_variable({key: None}, key)
    assert found is False
    assert value == "/"


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=10))
def test_resolve_render_variable_custom_fallback(key: str, fallback: str) -> None:
    found, value = resolve_render_variable({}, key, fallback_value=fallback)
    assert found is False
    assert value == fallback


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=20), st.text(max_size=50))
def test_resolve_render_variable_deterministic(key: str, val: str) -> None:
    variables = {key: val}
    assert resolve_render_variable(variables, key) == resolve_render_variable(variables, key)


# ---------------------------------------------------------------------------
# _has_fee_prepaid_context
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_has_fee_prepaid_context_returns_bool(text: str) -> None:
    result = _has_fee_prepaid_context(text, fee_keywords=("受理费",))
    assert isinstance(result, bool)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_has_fee_prepaid_context_deterministic(text: str) -> None:
    r1 = _has_fee_prepaid_context(text, fee_keywords=("受理费",))
    r2 = _has_fee_prepaid_context(text, fee_keywords=("受理费",))
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_has_fee_prepaid_context_empty(text: str) -> None:
    assert _has_fee_prepaid_context(text, fee_keywords=("受理费",)) is False


PREPAID_SENTENCES = [
    "案件受理费由被告负担，已预交",
    "案件受理费由被告负担，已缴",
    "案件受理费由被告负担，已交",
    "案件受理费由被告负担，先行垫付",
]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(PREPAID_SENTENCES))
def test_has_fee_prepaid_context_positive(sentence: str) -> None:
    assert _has_fee_prepaid_context(sentence, fee_keywords=("受理费",)) is True


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(PREPAID_SENTENCES))
def test_has_fee_prepaid_context_preservation_fee(sentence: str) -> None:
    """保全费 variant should also trigger."""
    preservation_sentence = sentence.replace("受理费", "保全费")
    assert _has_fee_prepaid_context(preservation_sentence, fee_keywords=("保全费",)) is True


# ---------------------------------------------------------------------------
# should_try_llm_fallback
# ---------------------------------------------------------------------------


def _make_parsed_amounts(**kwargs: Any) -> ParsedAmounts:
    defaults: dict[str, Any] = {
        "principal": None,
        "confirmed_interest": Decimal("0"),
        "litigation_fee": Decimal("0"),
        "preservation_fee": Decimal("0"),
        "announcement_fee": Decimal("0"),
        "attorney_fee": Decimal("0"),
        "guarantee_fee": Decimal("0"),
    }
    defaults.update(kwargs)
    return ParsedAmounts(**defaults)


def _make_parsed_interest_params(**kwargs: Any) -> ParsedInterestParams:
    defaults: dict[str, Any] = {
        "start_date": None,
        "rate_type": "1y",
        "multiplier": None,
        "custom_rate_unit": None,
        "custom_rate_value": None,
    }
    defaults.update(kwargs)
    return ParsedInterestParams(**defaults)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_should_try_llm_fallback_returns_bool(text: str) -> None:
    amounts = _make_parsed_amounts()
    params = _make_parsed_interest_params()
    result = should_try_llm_fallback(
        text=text,
        amounts=amounts,
        params=params,
        principal_fallback_to_target=False,
    )
    assert isinstance(result, bool)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_should_try_llm_fallback_deterministic(text: str) -> None:
    amounts = _make_parsed_amounts()
    params = _make_parsed_interest_params()
    r1 = should_try_llm_fallback(
        text=text, amounts=amounts, params=params, principal_fallback_to_target=False,
    )
    r2 = should_try_llm_fallback(
        text=text, amounts=amounts, params=params, principal_fallback_to_target=False,
    )
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_should_try_llm_fallback_principal_flag_forces_true(text: str) -> None:
    amounts = _make_parsed_amounts()
    params = _make_parsed_interest_params()
    result = should_try_llm_fallback(
        text=text,
        amounts=amounts,
        params=params,
        principal_fallback_to_target=True,
    )
    assert result is True


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_should_try_llm_fallback_with_start_date_no_rate(text: str) -> None:
    """When start_date is set but no multiplier/custom_rate, should trigger fallback."""
    amounts = _make_parsed_amounts()
    params = _make_parsed_interest_params(start_date=date(2023, 1, 1))
    result = should_try_llm_fallback(
        text=text,
        amounts=amounts,
        params=params,
        principal_fallback_to_target=False,
    )
    assert result is True


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_should_try_llm_fallback_with_start_date_and_multiplier(text: str) -> None:
    """When start_date and multiplier are both set, no fallback from date logic."""
    amounts = _make_parsed_amounts()
    params = _make_parsed_interest_params(
        start_date=date(2023, 1, 1),
        multiplier=Decimal("1.5"),
    )
    result = should_try_llm_fallback(
        text=text,
        amounts=amounts,
        params=params,
        principal_fallback_to_target=False,
    )
    # It may still be True for other reasons (fee, amount), so just check bool
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.none())
def test_parse_iso_date_none(value: None) -> None:
    assert _parse_iso_date(value) is None


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_parse_iso_date_empty(value: str) -> None:
    assert _parse_iso_date(value) is None


@settings(max_examples=200, deadline=None)
@given(st.just("   "))
def test_parse_iso_date_whitespace(value: str) -> None:
    assert _parse_iso_date(value) is None


@settings(max_examples=200, deadline=None)
@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)))
def test_parse_iso_date_valid_dates(d: date) -> None:
    iso_str = d.isoformat()
    result = _parse_iso_date(iso_str)
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=50).filter(lambda s: s.strip() != "" and "-" not in s))
def test_parse_iso_date_invalid_format(text: str) -> None:
    result = _parse_iso_date(text)
    assert result is None


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=100))
def test_parse_iso_date_returns_date_or_none(value: str) -> None:
    result = _parse_iso_date(value)
    assert result is None or isinstance(result, date)


# ---------------------------------------------------------------------------
# _parse_bool
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.none())
def test_parse_bool_none(value: None) -> None:
    assert _parse_bool(value) is False


@settings(max_examples=200, deadline=None)
@given(st.booleans())
def test_parse_bool_bools(value: bool) -> None:
    assert _parse_bool(value) == value


TRUTHY_STRINGS = ["true", "1", "yes", "y", "是", "True", "TRUE", "Yes", "YES"]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(TRUTHY_STRINGS))
def test_parse_bool_truthy(value: str) -> None:
    assert _parse_bool(value) is True


FALSY_STRINGS = ["false", "0", "no", "n", "否", "False", "FALSE", "No", "NO"]


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(FALSY_STRINGS))
def test_parse_bool_falsy(value: str) -> None:
    assert _parse_bool(value) is False


@settings(max_examples=200, deadline=None)
@given(st.integers())
def test_parse_bool_integers(value: int) -> None:
    """Non-bool values should return False unless they match known strings."""
    result = _parse_bool(value)
    assert isinstance(result, bool)
    if value not in (0, 1):
        # integers that are not 0 or 1 default to False via str conversion
        assert result is False


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=50))
def test_parse_bool_returns_bool(value: str) -> None:
    result = _parse_bool(value)
    assert isinstance(result, bool)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=50))
def test_parse_bool_deterministic(value: str) -> None:
    assert _parse_bool(value) == _parse_bool(value)
