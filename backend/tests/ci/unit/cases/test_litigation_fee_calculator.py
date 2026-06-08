"""诉讼费用计算服务单元测试。"""
from __future__ import annotations

import pytest
from decimal import Decimal

from apps.cases.services.data.litigation_fee_calculator_service import (
    DiscountType,
    LitigationFeeCalculatorService,
    PROPERTY_CASE_FEE_TIERS,
    PRESERVATION_FEE_MAX,
    IP_CASE_FEE_DEFAULT,
    DIVORCE_CASE_FEE_MIN,
    DIVORCE_CASE_FEE_MAX,
    PERSONALITY_RIGHTS_FEE_MIN,
    PERSONALITY_RIGHTS_FEE_MAX,
    BANKRUPTCY_FEE_MAX,
)
from apps.core.exceptions import ValidationException


@pytest.fixture
def svc() -> LitigationFeeCalculatorService:
    return LitigationFeeCalculatorService(cause_rule_service=None)


# ── _calculate_tiered_fee ──────────────────────────────────────────────────

def test_tiered_fee_zero_returns_first_tier_base(svc: LitigationFeeCalculatorService) -> None:
    """金额为 0 时返回第一段基础费用。"""
    result = svc._calculate_tiered_fee(Decimal("0"), PROPERTY_CASE_FEE_TIERS)
    assert result == Decimal("50")


def test_tiered_fee_negative_returns_first_tier_base(svc: LitigationFeeCalculatorService) -> None:
    """金额为负数时返回第一段基础费用。"""
    result = svc._calculate_tiered_fee(Decimal("-100"), PROPERTY_CASE_FEE_TIERS)
    assert result == Decimal("50")


def test_tiered_fee_within_first_tier(svc: LitigationFeeCalculatorService) -> None:
    """金额 <= 1 万，返回 50 元。"""
    result = svc.calculate_property_case_fee(Decimal("8000"))
    assert result == Decimal("50")


def test_tiered_fee_third_tier(svc: LitigationFeeCalculatorService) -> None:
    """金额 15 万，属于 10 万-20 万区间（第三段）。"""
    result = svc.calculate_property_case_fee(Decimal("150000"))
    assert result == Decimal("2300") + (Decimal("150000") - Decimal("100000")) * Decimal("0.02")


def test_tiered_fee_high_tier(svc: LitigationFeeCalculatorService) -> None:
    """金额 300 万，属于 200 万-500 万区间。"""
    result = svc.calculate_property_case_fee(Decimal("3000000"))
    assert result == Decimal("22800") + (Decimal("3000000") - Decimal("2000000")) * Decimal("0.008")


def test_tiered_fee_unlimited_top_tier(svc: LitigationFeeCalculatorService) -> None:
    """金额超 2000 万，最后一段无上限。"""
    result = svc.calculate_property_case_fee(Decimal("50000000"))
    assert result == Decimal("141800") + (Decimal("50000000") - Decimal("20000000")) * Decimal("0.005")


# ── calculate_preservation_fee ─────────────────────────────────────────────

def test_preservation_fee_small(svc: LitigationFeeCalculatorService) -> None:
    """保全金额 500，按 1% 计算。"""
    result = svc.calculate_preservation_fee(Decimal("500"))
    assert result == Decimal("30")


def test_preservation_fee_medium(svc: LitigationFeeCalculatorService) -> None:
    """保全金额 50 万，不超过上限。"""
    result = svc.calculate_preservation_fee(Decimal("500000"))
    expected = Decimal("1020") + (Decimal("500000") - Decimal("100000")) * Decimal("0.005")
    assert result == expected


def test_preservation_fee_capped(svc: LitigationFeeCalculatorService) -> None:
    """保全金额 1000 万，封顶 5000 元。"""
    result = svc.calculate_preservation_fee(Decimal("10000000"))
    assert result == PRESERVATION_FEE_MAX


def test_preservation_fee_negative(svc: LitigationFeeCalculatorService) -> None:
    """保全金额为负数时按 0 处理。"""
    result = svc.calculate_preservation_fee(Decimal("-100"))
    assert result == Decimal("30")


# ── calculate_execution_fee ────────────────────────────────────────────────

def test_execution_fee_small(svc: LitigationFeeCalculatorService) -> None:
    """执行金额 5000，返回 50 元。"""
    result = svc.calculate_execution_fee(Decimal("5000"))
    assert result == Decimal("50")


def test_execution_fee_medium(svc: LitigationFeeCalculatorService) -> None:
    """执行金额 30 万，属于 1 万-50 万区间。"""
    result = svc.calculate_execution_fee(Decimal("300000"))
    assert result == Decimal("50") + (Decimal("300000") - Decimal("10000")) * Decimal("0.015")


def test_execution_fee_negative(svc: LitigationFeeCalculatorService) -> None:
    """执行金额为负数时按 0 处理。"""
    result = svc.calculate_execution_fee(Decimal("-1"))
    assert result == Decimal("50")


# ── calculate_payment_order_fee ────────────────────────────────────────────

def test_payment_order_fee(svc: LitigationFeeCalculatorService) -> None:
    """支付令费用 = 财产案件费 / 3。"""
    amount = Decimal("50000")
    property_fee = svc.calculate_property_case_fee(amount)
    result = svc.calculate_payment_order_fee(amount)
    assert result == property_fee / Decimal("3")


# ── calculate_ip_case_fee ──────────────────────────────────────────────────

def test_ip_case_fee_no_amount(svc: LitigationFeeCalculatorService) -> None:
    """无争议金额返回固定 500 元。"""
    assert svc.calculate_ip_case_fee(None) == IP_CASE_FEE_DEFAULT


def test_ip_case_fee_zero(svc: LitigationFeeCalculatorService) -> None:
    """争议金额为 0 返回固定 500 元。"""
    assert svc.calculate_ip_case_fee(Decimal("0")) == IP_CASE_FEE_DEFAULT


def test_ip_case_fee_with_amount(svc: LitigationFeeCalculatorService) -> None:
    """有争议金额按财产案件标准计算。"""
    amount = Decimal("100000")
    assert svc.calculate_ip_case_fee(amount) == svc.calculate_property_case_fee(amount)


# ── calculate_divorce_case_fee ─────────────────────────────────────────────

def test_divorce_fee_no_property(svc: LitigationFeeCalculatorService) -> None:
    """无财产金额时返回基础费用。"""
    assert svc.calculate_divorce_case_fee(Decimal("150")) == Decimal("150")


def test_divorce_fee_property_under_threshold(svc: LitigationFeeCalculatorService) -> None:
    """财产不超过 20 万不另收费。"""
    assert svc.calculate_divorce_case_fee(Decimal("150"), Decimal("100000")) == Decimal("150")


def test_divorce_fee_property_over_threshold(svc: LitigationFeeCalculatorService) -> None:
    """财产超过 20 万的部分按 0.5% 计算。"""
    result = svc.calculate_divorce_case_fee(Decimal("150"), Decimal("300000"))
    expected = Decimal("150") + (Decimal("300000") - Decimal("200000")) * Decimal("0.005")
    assert result == expected


def test_divorce_fee_base_clamped_low(svc: LitigationFeeCalculatorService) -> None:
    """基础费用低于最低值时自动修正。"""
    result = svc.calculate_divorce_case_fee(Decimal("10"))
    assert result == DIVORCE_CASE_FEE_MIN


def test_divorce_fee_base_clamped_high(svc: LitigationFeeCalculatorService) -> None:
    """基础费用高于最高值时自动修正。"""
    result = svc.calculate_divorce_case_fee(Decimal("999"))
    assert result == DIVORCE_CASE_FEE_MAX


# ── calculate_personality_rights_fee ───────────────────────────────────────

def test_personality_rights_fee_no_damage(svc: LitigationFeeCalculatorService) -> None:
    """无损害赔偿金额时返回基础费用。"""
    assert svc.calculate_personality_rights_fee(Decimal("300")) == Decimal("300")


def test_personality_rights_fee_with_damage(svc: LitigationFeeCalculatorService) -> None:
    """有损害赔偿金额，按分段计算。"""
    result = svc.calculate_personality_rights_fee(Decimal("300"), Decimal("200000"))
    extra = svc._calculate_tiered_fee(Decimal("200000"), [
        (50000, Decimal("0"), Decimal("0")),
        (100000, Decimal("0.01"), Decimal("0")),
        (None, Decimal("0.005"), Decimal("500")),
    ])
    assert result == Decimal("300") + extra


def test_personality_rights_fee_base_clamped(svc: LitigationFeeCalculatorService) -> None:
    """基础费用自动修正到合法范围。"""
    assert svc.calculate_personality_rights_fee(Decimal("10")) == PERSONALITY_RIGHTS_FEE_MIN
    assert svc.calculate_personality_rights_fee(Decimal("999")) == PERSONALITY_RIGHTS_FEE_MAX


# ── calculate_bankruptcy_fee ───────────────────────────────────────────────

def test_bankruptcy_fee_normal(svc: LitigationFeeCalculatorService) -> None:
    """破产案件费 = 财产案件费 / 2。"""
    amount = Decimal("1000000")
    property_fee = svc.calculate_property_case_fee(amount)
    result = svc.calculate_bankruptcy_fee(amount)
    assert result == property_fee / Decimal("2")


def test_bankruptcy_fee_capped(svc: LitigationFeeCalculatorService) -> None:
    """破产案件费封顶 30 万。"""
    result = svc.calculate_bankruptcy_fee(Decimal("999999999"))
    assert result == BANKRUPTCY_FEE_MAX


def test_bankruptcy_fee_negative(svc: LitigationFeeCalculatorService) -> None:
    """破产金额为负数时按 0 处理。"""
    result = svc.calculate_bankruptcy_fee(Decimal("-100"))
    assert result == Decimal("25")  # 50 / 2


# ── apply_discount ─────────────────────────────────────────────────────────

def test_apply_discount_mediation(svc: LitigationFeeCalculatorService) -> None:
    """调解结案减半。"""
    assert svc.apply_discount(Decimal("1000"), DiscountType.MEDIATION) == Decimal("500")


def test_apply_discount_withdrawal(svc: LitigationFeeCalculatorService) -> None:
    """撤诉减半。"""
    assert svc.apply_discount(Decimal("1000"), DiscountType.WITHDRAWAL) == Decimal("500")


def test_apply_discount_simple(svc: LitigationFeeCalculatorService) -> None:
    """简易程序减半。"""
    assert svc.apply_discount(Decimal("1000"), DiscountType.SIMPLE_PROCEDURE) == Decimal("500")


def test_apply_discount_counterclaim(svc: LitigationFeeCalculatorService) -> None:
    """反诉合并减半。"""
    assert svc.apply_discount(Decimal("1000"), DiscountType.COUNTERCLAIM) == Decimal("500")


def test_apply_discount_unknown_type(svc: LitigationFeeCalculatorService) -> None:
    """未知减免类型不减免。"""
    assert svc.apply_discount(Decimal("1000"), "unknown") == Decimal("1000")


# ── validate_and_convert_fee_inputs ────────────────────────────────────────

def test_validate_inputs_valid(svc: LitigationFeeCalculatorService) -> None:
    """正常输入转换正确。"""
    target, preservation = svc.validate_and_convert_fee_inputs(100000.0, 50000.0)
    assert target == Decimal("100000.0")
    assert preservation == Decimal("50000.0")


def test_validate_inputs_none(svc: LitigationFeeCalculatorService) -> None:
    """None 值保持 None。"""
    target, preservation = svc.validate_and_convert_fee_inputs(None, None)
    assert target is None
    assert preservation is None


def test_validate_inputs_negative_target(svc: LitigationFeeCalculatorService) -> None:
    """涉案金额为负数抛出异常。"""
    with pytest.raises(ValidationException, match="涉案金额"):
        svc.validate_and_convert_fee_inputs(-1.0, None)


def test_validate_inputs_negative_preservation(svc: LitigationFeeCalculatorService) -> None:
    """保全金额为负数抛出异常。"""
    with pytest.raises(ValidationException, match="保全"):
        svc.validate_and_convert_fee_inputs(None, -1.0)


# ── calculate_personality_rights_fee_with_range ────────────────────────────

def test_personality_rights_range_no_amount(svc: LitigationFeeCalculatorService) -> None:
    """无金额返回基础范围。"""
    result = svc.calculate_personality_rights_fee_with_range(None)
    assert result["fee"] is None
    assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN
    assert result["fee_max"] == PERSONALITY_RIGHTS_FEE_MAX


def test_personality_rights_range_under_5w(svc: LitigationFeeCalculatorService) -> None:
    """金额 <= 5 万返回基础范围。"""
    result = svc.calculate_personality_rights_fee_with_range(Decimal("30000"))
    assert result["fee"] is None


def test_personality_rights_range_5w_to_10w(svc: LitigationFeeCalculatorService) -> None:
    """5 万 < 金额 <= 10 万时范围含额外费用。"""
    result = svc.calculate_personality_rights_fee_with_range(Decimal("80000"))
    extra = (Decimal("80000") - Decimal("50000")) * Decimal("0.01")
    assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN + extra


def test_personality_rights_range_over_10w(svc: LitigationFeeCalculatorService) -> None:
    """金额 > 10 万时范围含两段额外费用。"""
    result = svc.calculate_personality_rights_fee_with_range(Decimal("200000"))
    assert result["fee"] is None
    assert result["fee_min"] > PERSONALITY_RIGHTS_FEE_MIN


# ── calculate_ip_fee_with_range ────────────────────────────────────────────

def test_ip_range_no_amount(svc: LitigationFeeCalculatorService) -> None:
    """无金额返回固定费用范围。"""
    result = svc.calculate_ip_fee_with_range(None)
    assert result["fee"] is None
    assert "500-1000" in result["display_text"]


def test_ip_range_with_amount(svc: LitigationFeeCalculatorService) -> None:
    """有金额按财产案件标准计算。"""
    result = svc.calculate_ip_fee_with_range(Decimal("100000"))
    assert result["fee"] is not None
    assert result["fee_min"] == result["fee_max"]


# ── calculate_all_fees (integration-like) ──────────────────────────────────

def test_calculate_all_fees_labor(svc: LitigationFeeCalculatorService) -> None:
    """劳动争议案件返回固定费用 10 元。"""
    result = svc.calculate_all_fees(case_type="labor")
    assert result["fixed_fee"] == 10.0


def test_calculate_all_fees_admin_ip(svc: LitigationFeeCalculatorService) -> None:
    """行政 IP 案件返回固定费用 100 元。"""
    result = svc.calculate_all_fees(case_type="admin_ip")
    assert result["fixed_fee"] == 100.0


def test_calculate_all_fees_default_property(svc: LitigationFeeCalculatorService) -> None:
    """默认财产案件计算受理费和支付令费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("500000"), case_type=None)
    assert result["acceptance_fee"] is not None
    assert result["payment_order_fee"] is not None


def test_calculate_all_fees_with_preservation(svc: LitigationFeeCalculatorService) -> None:
    """有保全金额时计算保全费。"""
    result = svc.calculate_all_fees(
        target_amount=Decimal("500000"),
        preservation_amount=Decimal("200000"),
    )
    assert result["preservation_fee"] is not None


def test_calculate_all_fees_preservation_only(svc: LitigationFeeCalculatorService) -> None:
    """仅保全模式。"""
    result = svc.calculate_all_fees(case_type="preservation_only")
    assert any("保全" in d for d in result["calculation_details"])


def test_calculate_all_fees_no_amount(svc: LitigationFeeCalculatorService) -> None:
    """无金额时返回默认结果。"""
    result = svc.calculate_all_fees()
    assert result["acceptance_fee"] is None


def test_calculate_all_fees_execution(svc: LitigationFeeCalculatorService) -> None:
    """执行案件计算执行费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("300000"), case_type="execution")
    assert result["execution_fee"] is not None


def test_calculate_all_fees_bankruptcy(svc: LitigationFeeCalculatorService) -> None:
    """破产案件计算破产费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("1000000"), case_type="bankruptcy")
    assert result["bankruptcy_fee"] is not None


def test_calculate_all_fees_divorce(svc: LitigationFeeCalculatorService) -> None:
    """离婚案件计算离婚费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("300000"), case_type="divorce")
    assert result["divorce_fee"] is not None


def test_calculate_all_fees_personality_rights(svc: LitigationFeeCalculatorService) -> None:
    """人格权案件计算人格权费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("200000"), case_type="personality_rights")
    assert result["personality_rights_fee"] is not None


def test_calculate_all_fees_ip_with_amount(svc: LitigationFeeCalculatorService) -> None:
    """知识产权案件（有金额）计算 IP 费。"""
    result = svc.calculate_all_fees(target_amount=Decimal("500000"), case_type="ip_with_amount")
    assert result["ip_fee"] is not None
