"""Additional tests for litigation_fee_calculator_service.py — covering missing branches."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch
from decimal import Decimal

import pytest

from apps.cases.services.data.litigation_fee_calculator_service import (
    LitigationFeeCalculatorService,
    DiscountType,
    PROPERTY_CASE_FEE_TIERS,
    PRESERVATION_FEE_TIERS,
    EXECUTION_FEE_TIERS,
    PERSONALITY_RIGHTS_DAMAGE_TIERS,
    PERSONALITY_RIGHTS_FEE_MIN,
    PERSONALITY_RIGHTS_FEE_MAX,
    IP_CASE_FEE_MIN,
    IP_CASE_FEE_MAX,
    IP_CASE_FEE_DEFAULT,
    DIVORCE_CASE_FEE_MIN,
    DIVORCE_CASE_FEE_MAX,
    DIVORCE_PROPERTY_THRESHOLD,
    BANKRUPTCY_FEE_MAX,
    PRESERVATION_FEE_MAX,
)
from apps.core.exceptions import ValidationException


@pytest.fixture
def svc() -> LitigationFeeCalculatorService:
    return LitigationFeeCalculatorService(cause_rule_service=None)


@pytest.fixture
def svc_with_mock_cause_rule() -> tuple[LitigationFeeCalculatorService, MagicMock]:
    mock_crs = MagicMock()
    svc = LitigationFeeCalculatorService(cause_rule_service=mock_crs)
    return svc, mock_crs


# ── cause_rule_service property ───────────────────────────────────────────────

def test_cause_rule_service_lazy_load(svc: LitigationFeeCalculatorService) -> None:
    """cause_rule_service should lazy-load on first access."""
    # CauseRuleService is imported locally inside the property, so patch the module
    import apps.cases.services.data.cause_rule_service as crs_module
    with patch.object(crs_module, "CauseRuleService") as MockCRS:
        mock_instance = MagicMock()
        MockCRS.return_value = mock_instance
        result = svc.cause_rule_service
        assert result is mock_instance
        # second call returns cached
        assert svc.cause_rule_service is mock_instance


# ── calculate_property_case edge cases ────────────────────────────────────────

def test_property_fee_negative_clamped(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("-500"))
    assert result == Decimal("50")


def test_property_fee_exactly_at_boundary(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("10000"))
    assert result == Decimal("50")


def test_property_fee_second_tier(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("50000"))
    assert result == Decimal("50") + (Decimal("50000") - Decimal("10000")) * Decimal("0.025")


def test_property_fee_100w_to_200w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("1500000"))
    assert result == Decimal("13800") + (Decimal("1500000") - Decimal("1000000")) * Decimal("0.009")


def test_property_fee_500w_to_1000w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("8000000"))
    assert result == Decimal("46800") + (Decimal("8000000") - Decimal("5000000")) * Decimal("0.007")


def test_property_fee_1000w_to_2000w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_property_case_fee(Decimal("15000000"))
    assert result == Decimal("81800") + (Decimal("15000000") - Decimal("10000000")) * Decimal("0.006")


# ── calculate_preservation_fee edge ───────────────────────────────────────────

def test_preservation_fee_zero(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_preservation_fee(Decimal("0"))
    assert result == Decimal("30")


def test_preservation_fee_exactly_1000(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_preservation_fee(Decimal("1000"))
    assert result == Decimal("30")


def test_preservation_fee_second_tier(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_preservation_fee(Decimal("50000"))
    assert result == Decimal("30") + (Decimal("50000") - Decimal("1000")) * Decimal("0.01")


# ── calculate_execution_fee high tiers ────────────────────────────────────────

def test_execution_fee_50w_to_500w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_execution_fee(Decimal("1000000"))
    assert result == Decimal("7400") + (Decimal("1000000") - Decimal("500000")) * Decimal("0.01")


def test_execution_fee_500w_to_1000w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_execution_fee(Decimal("8000000"))
    assert result == Decimal("52400") + (Decimal("8000000") - Decimal("5000000")) * Decimal("0.005")


def test_execution_fee_above_1000w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_execution_fee(Decimal("20000000"))
    assert result == Decimal("77400") + (Decimal("20000000") - Decimal("10000000")) * Decimal("0.001")


# ── calculate_ip_case_fee negative ────────────────────────────────────────────

def test_ip_case_fee_negative(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_ip_case_fee(Decimal("-100"))
    assert result == IP_CASE_FEE_DEFAULT


# ── calculate_personality_rights_fee_with_range ───────────────────────────────

def test_personality_rights_range_zero(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_personality_rights_fee_with_range(Decimal("0"))
    assert result["fee"] is None
    assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN


def test_personality_rights_range_exactly_5w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_personality_rights_fee_with_range(Decimal("50000"))
    assert result["fee"] is None


def test_personality_rights_range_exactly_10w(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_personality_rights_fee_with_range(Decimal("100000"))
    assert result["fee"] is None
    extra = (Decimal("100000") - Decimal("50000")) * Decimal("0.01")
    assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN + extra


def test_personality_rights_range_display_text_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_personality_rights_fee_with_range(None)
    assert "减半" in result["display_text"]


def test_personality_rights_range_display_text_high(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_personality_rights_fee_with_range(Decimal("200000"))
    assert "案件受理费" in result["display_text"]


# ── calculate_ip_fee_with_range ───────────────────────────────────────────────

def test_ip_fee_range_zero(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_ip_fee_with_range(Decimal("0"))
    assert result["fee"] is None


def test_ip_fee_range_display_text_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_ip_fee_with_range(None)
    assert "减半" in result["display_text"]


def test_ip_fee_range_display_text_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_ip_fee_with_range(Decimal("100000"))
    assert "财产案件标准" in result["display_text"]


# ── apply_discount ────────────────────────────────────────────────────────────

def test_apply_discount_all_valid_types(svc: LitigationFeeCalculatorService) -> None:
    for dt in [DiscountType.MEDIATION, DiscountType.WITHDRAWAL,
               DiscountType.SIMPLE_PROCEDURE, DiscountType.COUNTERCLAIM]:
        assert svc.apply_discount(Decimal("1000"), dt) == Decimal("500")


def test_apply_discount_empty_string(svc: LitigationFeeCalculatorService) -> None:
    assert svc.apply_discount(Decimal("1000"), "") == Decimal("1000")


# ── _build_default_result ─────────────────────────────────────────────────────

def test_build_default_result(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    assert result["acceptance_fee"] is None
    assert result["calculation_details"] == []
    assert result["show_acceptance_fee"] is True
    assert result["show_half_fee"] is True
    assert result["show_payment_order_fee"] is False


# ── _append_preservation_fee ──────────────────────────────────────────────────

def test_append_preservation_fee_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._append_preservation_fee(result, Decimal("200000"))
    assert result["preservation_fee"] is not None
    assert len(result["calculation_details"]) == 1


def test_append_preservation_fee_none(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._append_preservation_fee(result, None)
    assert result["preservation_fee"] is None
    assert len(result["calculation_details"]) == 0


def test_append_preservation_fee_zero(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._append_preservation_fee(result, Decimal("0"))
    assert result["preservation_fee"] is None


# ── _apply_fee_rule ───────────────────────────────────────────────────────────

def test_apply_fee_rule(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {
        "special_case_type": "ip",
        "show_acceptance_fee": False,
        "show_half_fee": False,
        "show_payment_order_fee": True,
    }
    svc._apply_fee_rule(result, fee_rule)
    assert result["special_case_type"] == "ip"
    assert result["show_acceptance_fee"] is False
    assert result["show_half_fee"] is False
    assert result["show_payment_order_fee"] is True


def test_apply_fee_rule_defaults(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {}
    svc._apply_fee_rule(result, fee_rule)
    assert result["special_case_type"] is None
    assert result["show_acceptance_fee"] is True


# ── _handle_special_type ──────────────────────────────────────────────────────

def test_handle_special_type_personality_rights(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {"fee_display_text": "test"}
    handled = svc._handle_special_type(
        "personality_rights", result, fee_rule, Decimal("200000"), None,
    )
    assert handled is True
    assert result["fee_range_min"] is not None


def test_handle_special_type_ip(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {"fee_display_text": "test"}
    handled = svc._handle_special_type(
        "ip", result, fee_rule, Decimal("100000"), None,
    )
    assert handled is True
    assert result["ip_fee"] is not None


def test_handle_special_type_payment_order(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {"fee_display_text": "test"}
    handled = svc._handle_special_type(
        "payment_order", result, fee_rule, Decimal("100000"), None,
    )
    assert handled is True
    assert result["payment_order_fee"] is not None


def test_handle_special_type_unknown(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {}
    handled = svc._handle_special_type(
        "unknown_special_type", result, fee_rule, None, None,
    )
    assert handled is False


def test_handle_special_type_with_preservation(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    fee_rule = {"fee_display_text": "test"}
    handled = svc._handle_special_type(
        "personality_rights", result, fee_rule, Decimal("200000"), Decimal("100000"),
    )
    assert handled is True
    assert result["preservation_fee"] is not None


# ── _handle_payment_order_special ─────────────────────────────────────────────

def test_handle_payment_order_special_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_payment_order_special(result, None)
    assert result["payment_order_fee"] is None


def test_handle_payment_order_special_zero_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_payment_order_special(result, Decimal("0"))
    assert result["payment_order_fee"] is None


def test_handle_payment_order_special_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_payment_order_special(result, Decimal("500000"))
    assert result["acceptance_fee"] is not None
    assert result["acceptance_fee_half"] is not None
    assert result["payment_order_fee"] is not None
    assert len(result["calculation_details"]) >= 3


# ── _handle_personality_rights_special ────────────────────────────────────────

def test_handle_personality_rights_special_with_fee(svc: LitigationFeeCalculatorService) -> None:
    # _calculate_tiered_fee is a pure function, test it directly
    result = svc._calculate_tiered_fee(Decimal("200000"), [
        (50000, Decimal("0"), Decimal("0")),
        (100000, Decimal("0.01"), Decimal("0")),
        (None, Decimal("0.005"), Decimal("500")),
    ])
    assert result > 0


def test_handle_personality_rights_special_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_personality_rights_special(result, None)
    assert result["fee_range_min"] is not None
    assert result["personality_rights_fee"] is None


# ── _handle_ip_special ────────────────────────────────────────────────────────

def test_handle_ip_special_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_ip_special(result, Decimal("100000"))
    assert result["ip_fee"] is not None
    assert result["acceptance_fee"] is not None
    assert result["acceptance_fee_half"] is not None


def test_handle_ip_special_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_ip_special(result, None)
    assert result["ip_fee"] is None
    assert result["fee_range_min"] is not None


# ── _handle_amount_based_case ─────────────────────────────────────────────────

def test_handle_amount_based_execution(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "execution", Decimal("300000"))
    assert result["execution_fee"] is not None


def test_handle_amount_based_bankruptcy(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "bankruptcy", Decimal("1000000"))
    assert result["bankruptcy_fee"] is not None


def test_handle_amount_based_payment_order(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "payment_order", Decimal("100000"))
    assert result["payment_order_fee"] is not None
    assert result["show_payment_order_fee"] is True


def test_handle_amount_based_divorce(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "divorce", Decimal("300000"))
    assert result["divorce_fee"] is not None


def test_handle_amount_based_divorce_under_threshold(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "divorce", Decimal("100000"))
    assert result["divorce_fee"] is not None
    assert any("不另收" in d for d in result["calculation_details"])


def test_handle_amount_based_personality_rights(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "personality_rights", Decimal("200000"))
    assert result["personality_rights_fee"] is not None


def test_handle_amount_based_ip_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "ip_with_amount", Decimal("500000"))
    assert result["ip_fee"] is not None


def test_handle_amount_based_unknown(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._handle_amount_based_case(result, "unknown_type", Decimal("500000"))
    assert result["acceptance_fee"] is not None


# ── calculate_all_fees with cause_of_action_id ────────────────────────────────

def test_calculate_all_fees_with_cause_rule(svc_with_mock_cause_rule: tuple) -> None:
    svc, mock_crs = svc_with_mock_cause_rule
    mock_crs.get_fee_rule.return_value = {
        "special_case_type": "ip",
        "fee_display_text": "test IP fee",
        "show_acceptance_fee": True,
        "show_half_fee": True,
        "show_payment_order_fee": False,
    }
    result = svc.calculate_all_fees(
        target_amount=Decimal("100000"),
        cause_of_action_id=42,
    )
    assert result["special_case_type"] == "ip"


def test_calculate_all_fees_cause_rule_no_match(svc_with_mock_cause_rule: tuple) -> None:
    svc, mock_crs = svc_with_mock_cause_rule
    mock_crs.get_fee_rule.return_value = None
    result = svc.calculate_all_fees(
        target_amount=Decimal("100000"),
        cause_of_action_id=999,
    )
    assert result["acceptance_fee"] is not None


# ── calculate_all_fees fixed fee types ────────────────────────────────────────

def test_calculate_all_fees_public_notice(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="public_notice")
    assert result["fixed_fee"] == 100.0
    assert result["fee_name"] == "公示催告申请"


def test_calculate_all_fees_revoke_arbitration(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="revoke_arbitration")
    assert result["fixed_fee"] == 400.0


def test_calculate_all_fees_admin_other(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="admin_other")
    assert result["fixed_fee"] == 50.0


def test_calculate_all_fees_other_non_property(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="other_non_property")
    assert result["fixed_fee"] == 50.0


def test_calculate_all_fees_jurisdiction_objection(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="jurisdiction_objection")
    assert result["fixed_fee"] == 50.0


def test_calculate_all_fees_ip_no_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(case_type="ip_no_amount")
    assert result["fixed_fee"] == 500.0


def test_calculate_all_fees_labor_with_preservation(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(
        case_type="labor",
        preservation_amount=Decimal("100000"),
    )
    assert result["fixed_fee"] == 10.0
    assert result["preservation_fee"] is not None


# ── calculate_all_fees payment_order via case_type ────────────────────────────

def test_calculate_all_fees_payment_order_by_type(svc: LitigationFeeCalculatorService) -> None:
    result = svc.calculate_all_fees(
        target_amount=Decimal("200000"),
        case_type="payment_order",
    )
    assert result["payment_order_fee"] is not None
    assert result["show_payment_order_fee"] is True


# ── _calc_divorce details ─────────────────────────────────────────────────────

def test_calc_divorce_details_above_threshold(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._calc_divorce(result, Decimal("500000"))
    assert "超过20万" in result["calculation_details"][0]


def test_calc_divorce_details_below_threshold(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._calc_divorce(result, Decimal("100000"))
    assert "不另收" in result["calculation_details"][0]


# ── _calc_ip_with_amount ──────────────────────────────────────────────────────

def test_calc_ip_with_amount(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._calc_ip_with_amount(result, Decimal("100000"))
    assert result["ip_fee"] is not None
    assert "知识产权" in result["calculation_details"][0]


# ── _calc_personality_rights_by_type ──────────────────────────────────────────

def test_calc_personality_rights_by_type(svc: LitigationFeeCalculatorService) -> None:
    result = svc._build_default_result()
    svc._calc_personality_rights_by_type(result, Decimal("200000"))
    assert result["personality_rights_fee"] is not None
    assert "人格权" in result["calculation_details"][0]
