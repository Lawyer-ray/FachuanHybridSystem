"""Property-based tests for execution_request_interest module."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.services.placeholders.litigation.execution_request_interest import (
    apply_paid_amount,
    calculate_interest,
    detect_overdue_item_label,
    parse_deduction_order,
    parse_interest_base_rule,
    parse_interest_params,
    resolve_interest_base,
)
from apps.documents.services.placeholders.litigation.execution_request_models import (
    InterestSegment,
    ParsedAmounts,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

positive_decimal = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("10000000"),
    allow_nan=False, allow_infinity=False, places=2,
)

non_negative_decimal = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("10000000"),
    allow_nan=False, allow_infinity=False, places=2,
)


def _make_amounts(
    principal: Decimal | None = None,
    confirmed_interest: Decimal = Decimal("0"),
    litigation_fee: Decimal = Decimal("0"),
    preservation_fee: Decimal = Decimal("0"),
    announcement_fee: Decimal = Decimal("0"),
    attorney_fee: Decimal = Decimal("0"),
    guarantee_fee: Decimal = Decimal("0"),
) -> ParsedAmounts:
    return ParsedAmounts(
        principal=principal,
        confirmed_interest=confirmed_interest,
        litigation_fee=litigation_fee,
        preservation_fee=preservation_fee,
        announcement_fee=announcement_fee,
        attorney_fee=attorney_fee,
        guarantee_fee=guarantee_fee,
    )


# ---------------------------------------------------------------------------
# parse_interest_params
# ---------------------------------------------------------------------------


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_parse_interest_params_returns_dataclass_empty(text: str) -> None:
    result = parse_interest_params(text)
    assert isinstance(result, ParsedInterestParams)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_params_custom_rate_unit_valid(text: str) -> None:
    result = parse_interest_params(text)
    if result.custom_rate_unit is not None:
        assert result.custom_rate_unit in {"percent", "permille", "permyriad"}


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_params_rate_type_valid(text: str) -> None:
    result = parse_interest_params(text)
    assert result.rate_type in {"1y", "5y"}


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_params_base_mode_valid(text: str) -> None:
    valid_modes = {"fixed_amount", "fixed_amount_remaining", "remaining_principal", "remaining_total", "fallback_target"}
    result = parse_interest_params(text)
    assert result.base_mode in valid_modes


# ---------------------------------------------------------------------------
# detect_overdue_item_label
# ---------------------------------------------------------------------------

KNOWN_LABELS = {"利息", "逾期利息", "逾期付款利息", "违约金", "逾期付款违约金", "逾期付款损失"}


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_detect_overdue_item_label_empty_returns_lixi(text: str) -> None:
    assert detect_overdue_item_label(text) == "利息"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_detect_overdue_item_label_output_in_known_set(text: str) -> None:
    result = detect_overdue_item_label(text)
    assert result in KNOWN_LABELS, f"Unexpected label: {result!r}"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_detect_overdue_item_label_deterministic(text: str) -> None:
    assert detect_overdue_item_label(text) == detect_overdue_item_label(text)


# ---------------------------------------------------------------------------
# parse_interest_base_rule
# ---------------------------------------------------------------------------

VALID_BASE_MODES = {"fixed_amount", "fixed_amount_remaining", "remaining_principal", "remaining_total", "fallback_target"}


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_base_rule_mode_valid(text: str) -> None:
    mode, amount = parse_interest_base_rule(rate_text=text, full_text=text)
    assert mode in VALID_BASE_MODES


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_base_rule_fixed_amount_positive(text: str) -> None:
    mode, amount = parse_interest_base_rule(rate_text=text, full_text=text)
    if mode in {"fixed_amount", "fixed_amount_remaining"} and amount is not None:
        assert amount > Decimal("0"), f"fixed_amount mode but base_amount={amount} <= 0"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_interest_base_rule_non_fixed_has_no_amount(text: str) -> None:
    mode, amount = parse_interest_base_rule(rate_text=text, full_text=text)
    if mode in {"remaining_principal", "remaining_total", "fallback_target"}:
        assert amount is None


# ---------------------------------------------------------------------------
# parse_deduction_order
# ---------------------------------------------------------------------------

VALID_DEDUCTION_KEYS = {"litigation_fee", "preservation_fee", "announcement_fee", "attorney_fee", "guarantee_fee", "interest", "principal"}


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_parse_deduction_order_empty_text(text: str) -> None:
    assert parse_deduction_order(text) == []


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_deduction_order_all_from_known_set(text: str) -> None:
    result = parse_deduction_order(text)
    for key in result:
        assert key in VALID_DEDUCTION_KEYS, f"Unknown deduction key: {key!r}"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1000))
def test_parse_deduction_order_no_duplicates(text: str) -> None:
    result = parse_deduction_order(text)
    assert len(result) == len(set(result)), f"Duplicates in {result}"


# ---------------------------------------------------------------------------
# apply_paid_amount
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal)
def test_apply_paid_amount_zero_paid_no_change(paid: Decimal) -> None:
    """When paid_amount is 0, components should not change."""
    original_principal = Decimal("1000")
    amounts = _make_amounts(principal=original_principal, confirmed_interest=Decimal("200"))
    deduction_order = ["interest", "principal"]

    result_amounts, principal_paid, applied = apply_paid_amount(
        amounts=amounts, paid_amount=Decimal("0"), deduction_order=deduction_order,
    )
    assert principal_paid == Decimal("0")
    assert result_amounts.principal == original_principal
    assert len(applied) == 0


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, st.lists(st.sampled_from(["interest", "principal"]), min_size=0, max_size=4))
def test_apply_paid_amount_components_non_negative(paid: Decimal, order: list[str]) -> None:
    amounts = _make_amounts(principal=Decimal("5000"), confirmed_interest=Decimal("1000"))
    result_amounts, principal_paid, applied = apply_paid_amount(
        amounts=amounts, paid_amount=paid, deduction_order=order,
    )
    assert result_amounts.principal is None or result_amounts.principal >= Decimal("0")
    assert result_amounts.confirmed_interest >= Decimal("0")
    assert result_amounts.litigation_fee >= Decimal("0")
    assert result_amounts.preservation_fee >= Decimal("0")
    assert result_amounts.announcement_fee >= Decimal("0")
    assert result_amounts.attorney_fee >= Decimal("0")
    assert result_amounts.guarantee_fee >= Decimal("0")


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, st.lists(st.sampled_from(["interest", "principal"]), min_size=0, max_size=4))
def test_apply_paid_amount_deduction_leq_paid(paid: Decimal, order: list[str]) -> None:
    amounts = _make_amounts(principal=Decimal("5000"), confirmed_interest=Decimal("1000"))
    result_amounts, principal_paid, applied = apply_paid_amount(
        amounts=amounts, paid_amount=paid, deduction_order=order,
    )
    total_deducted = sum((item["amount"] for item in applied), Decimal("0"))
    assert total_deducted <= max(paid, Decimal("0")), (
        f"Total deducted {total_deducted} > paid {paid}"
    )


# ---------------------------------------------------------------------------
# calculate_interest
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.decimals(max_value=Decimal("0"), allow_nan=False, allow_infinity=False, places=2))
def test_calculate_interest_non_positive_principal_returns_zero(principal: Decimal) -> None:
    """When principal <= 0, interest must be 0."""
    calculator = MagicMock()
    params = ParsedInterestParams(start_date=date(2023, 1, 1))
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=date(2023, 12, 31),
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result == Decimal("0")


@settings(max_examples=200, deadline=None)
@given(positive_decimal)
def test_calculate_interest_no_start_date_returns_zero(principal: Decimal) -> None:
    calculator = MagicMock()
    params = ParsedInterestParams(start_date=None)
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=date(2023, 12, 31),
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result == Decimal("0")


@settings(max_examples=200, deadline=None)
@given(positive_decimal)
def test_calculate_interest_no_rate_returns_zero(principal: Decimal) -> None:
    calculator = MagicMock()
    params = ParsedInterestParams(start_date=date(2023, 1, 1), multiplier=None, custom_rate_value=None)
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=date(2023, 12, 31),
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result == Decimal("0")


@settings(max_examples=200, deadline=None)
@given(positive_decimal, st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 31)))
def test_calculate_interest_cutoff_before_start_returns_zero(principal: Decimal, cutoff: date) -> None:
    start = date(2024, 1, 1)
    assume(cutoff < start)
    calculator = MagicMock()
    params = ParsedInterestParams(start_date=start, multiplier=Decimal("1"))
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=cutoff,
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result == Decimal("0")
    assert any("截止日早于利息起算日" in w for w in warnings)


@settings(max_examples=200, deadline=None)
@given(positive_decimal, st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000000"), allow_nan=False, allow_infinity=False, places=2))
def test_calculate_interest_capped_when_cap_set(principal: Decimal, cap: Decimal) -> None:
    """When interest_cap is set, returned interest should not exceed it."""
    calculator = MagicMock()
    # Mock the calculator to return interest higher than the cap
    mock_result = MagicMock()
    mock_result.total_interest = cap + Decimal("100")
    calculator.calculate.return_value = mock_result

    params = ParsedInterestParams(
        start_date=date(2023, 1, 1),
        multiplier=Decimal("1.5"),
        interest_cap=cap,
    )
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=date(2023, 12, 31),
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result <= cap, f"Interest {result} exceeds cap {cap}"


@settings(max_examples=200, deadline=None)
@given(positive_decimal)
def test_calculate_interest_non_negative(principal: Decimal) -> None:
    calculator = MagicMock()
    mock_result = MagicMock()
    mock_result.total_interest = Decimal("500")
    calculator.calculate.return_value = mock_result

    params = ParsedInterestParams(
        start_date=date(2023, 1, 1),
        multiplier=Decimal("1"),
    )
    warnings: list[str] = []
    result = calculate_interest(
        calculator=calculator,
        principal=principal,
        params=params,
        cutoff_date=date(2023, 12, 31),
        year_days=365,
        date_inclusion="both",
        warnings=warnings,
    )
    assert result >= Decimal("0")


# ---------------------------------------------------------------------------
# resolve_interest_base
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, non_negative_decimal, non_negative_decimal)
def test_resolve_interest_base_returns_non_negative(
    principal: Decimal,
    confirmed_interest: Decimal,
    principal_paid: Decimal,
) -> None:
    amounts = _make_amounts(principal=principal, confirmed_interest=confirmed_interest)
    params = ParsedInterestParams(base_mode="remaining_principal")
    case = MagicMock()
    case.target_amount = None

    result = resolve_interest_base(
        case=case, amounts=amounts, params=params, principal_paid=principal_paid,
    )
    assert result >= Decimal("0"), f"resolve_interest_base returned {result} < 0"


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, non_negative_decimal)
def test_resolve_interest_base_fixed_mode(
    base_amount: Decimal,
    principal_paid: Decimal,
) -> None:
    assume(base_amount > 0)
    amounts = _make_amounts(principal=Decimal("0"))
    params = ParsedInterestParams(base_mode="fixed_amount", base_amount=base_amount)
    case = MagicMock()
    case.target_amount = None

    result = resolve_interest_base(
        case=case, amounts=amounts, params=params, principal_paid=principal_paid,
    )
    assert result >= Decimal("0")


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, non_negative_decimal)
def test_resolve_interest_base_remaining_total(
    principal: Decimal,
    confirmed_interest: Decimal,
) -> None:
    amounts = _make_amounts(principal=principal, confirmed_interest=confirmed_interest)
    params = ParsedInterestParams(base_mode="remaining_total")
    case = MagicMock()
    case.target_amount = None

    result = resolve_interest_base(
        case=case, amounts=amounts, params=params, principal_paid=Decimal("0"),
    )
    assert result >= Decimal("0")


@settings(max_examples=200, deadline=None)
@given(non_negative_decimal, non_negative_decimal)
def test_resolve_interest_base_fallback_with_target(
    target_amount: Decimal,
    principal: Decimal,
) -> None:
    assume(target_amount > 0)
    amounts = _make_amounts(principal=principal)
    params = ParsedInterestParams(base_mode="fallback_target")
    case = MagicMock()
    case.target_amount = target_amount

    result = resolve_interest_base(
        case=case, amounts=amounts, params=params, principal_paid=Decimal("0"),
    )
    assert result >= Decimal("0")
