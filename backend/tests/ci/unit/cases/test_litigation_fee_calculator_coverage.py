"""Cases: LitigationFeeCalculatorService comprehensive tests."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


class TestLitigationFeeCalculatorServiceMethods:
    """LitigationFeeCalculatorService methods that execute real code."""

    def _make_service(self):
        from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

        return LitigationFeeCalculatorService(cause_rule_service=MagicMock())

    def test_calculate_tiered_fee_zero(self):
        svc = self._make_service()
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        result = svc._calculate_tiered_fee(Decimal("0"), PROPERTY_CASE_FEE_TIERS)
        assert result == Decimal("50")

    def test_calculate_tiered_fee_negative(self):
        svc = self._make_service()
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        result = svc._calculate_tiered_fee(Decimal("-100"), PROPERTY_CASE_FEE_TIERS)
        assert result == Decimal("50")

    def test_calculate_tiered_fee_first_tier(self):
        svc = self._make_service()
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        result = svc._calculate_tiered_fee(Decimal("5000"), PROPERTY_CASE_FEE_TIERS)
        assert result == Decimal("50")

    def test_calculate_tiered_fee_second_tier(self):
        svc = self._make_service()
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        result = svc._calculate_tiered_fee(Decimal("50000"), PROPERTY_CASE_FEE_TIERS)
        assert result > Decimal("50")

    def test_calculate_tiered_fee_high_tier(self):
        svc = self._make_service()
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        result = svc._calculate_tiered_fee(Decimal("30000000"), PROPERTY_CASE_FEE_TIERS)
        assert result > Decimal("141800")

    def test_calculate_property_case_fee(self):
        svc = self._make_service()
        result = svc.calculate_property_case_fee(Decimal("100000"))
        assert result > Decimal("0")

    def test_calculate_property_case_fee_negative(self):
        svc = self._make_service()
        result = svc.calculate_property_case_fee(Decimal("-1"))
        assert result == Decimal("50")

    def test_calculate_preservation_fee(self):
        svc = self._make_service()
        result = svc.calculate_preservation_fee(Decimal("50000"))
        assert result > Decimal("0")
        assert result <= Decimal("5000")

    def test_calculate_preservation_fee_max_cap(self):
        svc = self._make_service()
        result = svc.calculate_preservation_fee(Decimal("10000000"))
        assert result == Decimal("5000")

    def test_calculate_preservation_fee_negative(self):
        svc = self._make_service()
        result = svc.calculate_preservation_fee(Decimal("-1"))
        assert result >= Decimal("0")

    def test_calculate_execution_fee(self):
        svc = self._make_service()
        result = svc.calculate_execution_fee(Decimal("100000"))
        assert result > Decimal("0")

    def test_calculate_execution_fee_negative(self):
        svc = self._make_service()
        result = svc.calculate_execution_fee(Decimal("-1"))
        assert result == Decimal("50")

    def test_calculate_payment_order_fee(self):
        svc = self._make_service()
        result = svc.calculate_payment_order_fee(Decimal("100000"))
        assert result > Decimal("0")

    def test_calculate_ip_case_fee_none(self):
        svc = self._make_service()
        result = svc.calculate_ip_case_fee(None)
        assert result == Decimal("500")

    def test_calculate_ip_case_fee_zero(self):
        svc = self._make_service()
        result = svc.calculate_ip_case_fee(Decimal("0"))
        assert result == Decimal("500")

    def test_calculate_ip_case_fee_with_amount(self):
        svc = self._make_service()
        result = svc.calculate_ip_case_fee(Decimal("100000"))
        assert result > Decimal("500")

    def test_calculate_divorce_case_fee_basic(self):
        svc = self._make_service()
        result = svc.calculate_divorce_case_fee(Decimal("150"))
        assert result == Decimal("150")

    def test_calculate_divorce_case_fee_below_min(self):
        svc = self._make_service()
        result = svc.calculate_divorce_case_fee(Decimal("10"))
        assert result == Decimal("50")  # min

    def test_calculate_divorce_case_fee_above_max(self):
        svc = self._make_service()
        result = svc.calculate_divorce_case_fee(Decimal("500"))
        assert result == Decimal("300")  # max

    def test_calculate_divorce_case_fee_with_property(self):
        svc = self._make_service()
        result = svc.calculate_divorce_case_fee(Decimal("150"), Decimal("300000"))
        assert result > Decimal("150")

    def test_calculate_divorce_case_fee_property_below_threshold(self):
        svc = self._make_service()
        result = svc.calculate_divorce_case_fee(Decimal("150"), Decimal("100000"))
        assert result == Decimal("150")

    def test_calculate_personality_rights_fee_basic(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee(Decimal("300"))
        assert result == Decimal("300")

    def test_calculate_personality_rights_fee_below_min(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee(Decimal("50"))
        assert result == Decimal("100")

    def test_calculate_personality_rights_fee_above_max(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee(Decimal("1000"))
        assert result == Decimal("500")

    def test_calculate_personality_rights_fee_with_damage(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee(Decimal("300"), Decimal("200000"))
        assert result > Decimal("300")

    def test_calculate_bankruptcy_fee(self):
        svc = self._make_service()
        result = svc.calculate_bankruptcy_fee(Decimal("1000000"))
        assert result > Decimal("0")
        assert result <= Decimal("300000")

    def test_calculate_bankruptcy_fee_max_cap(self):
        svc = self._make_service()
        result = svc.calculate_bankruptcy_fee(Decimal("1000000000"))
        assert result == Decimal("300000")

    def test_calculate_bankruptcy_fee_negative(self):
        svc = self._make_service()
        result = svc.calculate_bankruptcy_fee(Decimal("-1"))
        assert result >= Decimal("0")

    def test_calculate_personality_rights_fee_with_range_none(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee_with_range(None)
        assert result["fee"] is None
        assert result["fee_min"] == Decimal("100")
        assert result["fee_max"] == Decimal("500")

    def test_calculate_personality_rights_fee_with_range_zero(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee_with_range(Decimal("0"))
        assert result["fee"] is None

    def test_calculate_personality_rights_fee_with_range_low(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee_with_range(Decimal("30000"))
        assert result["fee"] is None

    def test_calculate_personality_rights_fee_with_range_mid(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee_with_range(Decimal("80000"))
        assert result["fee"] is None
        assert result["fee_min"] > Decimal("100")

    def test_calculate_personality_rights_fee_with_range_high(self):
        svc = self._make_service()
        result = svc.calculate_personality_rights_fee_with_range(Decimal("200000"))
        assert result["fee"] is None
        assert result["fee_min"] > Decimal("100")

    def test_calculate_ip_fee_with_range_none(self):
        svc = self._make_service()
        result = svc.calculate_ip_fee_with_range(None)
        assert result["fee"] is None

    def test_calculate_ip_fee_with_range_with_amount(self):
        svc = self._make_service()
        result = svc.calculate_ip_fee_with_range(Decimal("100000"))
        assert result["fee"] is not None

    def test_apply_discount_mediation(self):
        svc = self._make_service()
        result = svc.apply_discount(Decimal("1000"), "mediation")
        assert result == Decimal("500")

    def test_apply_discount_withdrawal(self):
        svc = self._make_service()
        result = svc.apply_discount(Decimal("1000"), "withdrawal")
        assert result == Decimal("500")

    def test_apply_discount_simple(self):
        svc = self._make_service()
        result = svc.apply_discount(Decimal("1000"), "simple")
        assert result == Decimal("500")

    def test_apply_discount_counterclaim(self):
        svc = self._make_service()
        result = svc.apply_discount(Decimal("1000"), "counterclaim")
        assert result == Decimal("500")

    def test_apply_discount_unknown(self):
        svc = self._make_service()
        result = svc.apply_discount(Decimal("1000"), "unknown")
        assert result == Decimal("1000")

    def test_build_default_result(self):
        svc = self._make_service()
        result = svc._build_default_result()
        assert "acceptance_fee" in result
        assert "preservation_fee" in result
        assert result["show_acceptance_fee"] is True

    def test_append_preservation_fee_with_amount(self):
        svc = self._make_service()
        result = svc._build_default_result()
        svc._append_preservation_fee(result, Decimal("50000"))
        assert result["preservation_fee"] is not None
        assert len(result["calculation_details"]) > 0

    def test_append_preservation_fee_none(self):
        svc = self._make_service()
        result = svc._build_default_result()
        svc._append_preservation_fee(result, None)
        assert result["preservation_fee"] is None

    def test_apply_fee_rule(self):
        svc = self._make_service()
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

    def test_validate_and_convert_fee_inputs_valid(self):
        svc = self._make_service()
        target, preserv = svc.validate_and_convert_fee_inputs(100000.0, 50000.0)
        assert target == Decimal("100000.0")
        assert preserv == Decimal("50000.0")

    def test_validate_and_convert_fee_inputs_none(self):
        svc = self._make_service()
        target, preserv = svc.validate_and_convert_fee_inputs(None, None)
        assert target is None
        assert preserv is None

    def test_validate_and_convert_fee_inputs_negative_target(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.validate_and_convert_fee_inputs(-100.0, None)

    def test_validate_and_convert_fee_inputs_negative_preservation(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.validate_and_convert_fee_inputs(None, -100.0)

    def test_calculate_all_fees_default(self):
        svc = self._make_service()
        result = svc.calculate_all_fees()
        assert "acceptance_fee" in result

    def test_calculate_all_fees_with_amount(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("100000"))
        assert result["acceptance_fee"] is not None

    def test_calculate_all_fees_with_preservation(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(preservation_amount=Decimal("50000"))
        assert result["preservation_fee"] is not None

    def test_calculate_all_fees_fixed_type_labor(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(case_type="labor")
        assert result["fixed_fee"] == float(Decimal("10"))

    def test_calculate_all_fees_fixed_type_public_notice(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(case_type="public_notice")
        assert result["fixed_fee"] == float(Decimal("100"))

    def test_calculate_all_fees_execution(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("100000"), case_type="execution")
        assert result["execution_fee"] is not None

    def test_calculate_all_fees_bankruptcy(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("1000000"), case_type="bankruptcy")
        assert result["bankruptcy_fee"] is not None

    def test_calculate_all_fees_payment_order(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("100000"), case_type="payment_order")
        assert result["payment_order_fee"] is not None

    def test_calculate_all_fees_divorce(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("300000"), case_type="divorce")
        assert result["divorce_fee"] is not None

    def test_calculate_all_fees_personality_rights(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("200000"), case_type="personality_rights")
        assert result["personality_rights_fee"] is not None

    def test_calculate_all_fees_ip_with_amount(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(target_amount=Decimal("100000"), case_type="ip_with_amount")
        assert result["ip_fee"] is not None

    def test_calculate_all_fees_preservation_only(self):
        svc = self._make_service()
        result = svc.calculate_all_fees(case_type="preservation_only")
        assert len(result["calculation_details"]) > 0

    def test_calculate_all_fees_with_cause_rule(self):
        svc = self._make_service()
        svc.cause_rule_service.get_fee_rule.return_value = {
            "special_case_type": "personality_rights",
            "fee_display_text": "人格权案件",
            "show_acceptance_fee": True,
            "show_half_fee": True,
            "show_payment_order_fee": False,
        }
        result = svc.calculate_all_fees(
            target_amount=Decimal("50000"),
            cause_of_action_id=1,
        )
        assert result["special_case_type"] == "personality_rights"

    def test_calculate_all_fees_with_cause_rule_ip(self):
        svc = self._make_service()
        svc.cause_rule_service.get_fee_rule.return_value = {
            "special_case_type": "ip",
            "fee_display_text": "知识产权案件",
            "show_acceptance_fee": True,
            "show_half_fee": True,
            "show_payment_order_fee": False,
        }
        result = svc.calculate_all_fees(
            target_amount=Decimal("100000"),
            cause_of_action_id=2,
        )
        assert result["special_case_type"] == "ip"

    def test_calculate_all_fees_with_cause_rule_payment_order(self):
        svc = self._make_service()
        svc.cause_rule_service.get_fee_rule.return_value = {
            "special_case_type": "payment_order",
            "fee_display_text": "支付令",
            "show_acceptance_fee": True,
            "show_half_fee": True,
            "show_payment_order_fee": True,
        }
        result = svc.calculate_all_fees(
            target_amount=Decimal("100000"),
            cause_of_action_id=3,
        )
        assert result["special_case_type"] == "payment_order"

    def test_calculate_all_fees_with_cause_rule_fixed_fee(self):
        svc = self._make_service()
        svc.cause_rule_service.get_fee_rule.return_value = {
            "special_case_type": "labor",
            "fee_display_text": "劳动争议",
            "show_acceptance_fee": True,
            "show_half_fee": True,
            "show_payment_order_fee": False,
        }
        from apps.cases.services.data.cause_rule_service import FIXED_FEES

        with patch.dict(FIXED_FEES, {"labor": Decimal("10")}, clear=False):
            result = svc.calculate_all_fees(
                cause_of_action_id=4,
            )
            assert result["fixed_fee"] == float(Decimal("10"))

    def test_cause_rule_service_lazy_load(self):
        from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

        svc = LitigationFeeCalculatorService(cause_rule_service=None)
        with patch(
            "apps.cases.services.data.litigation_fee_calculator_service.LitigationFeeCalculatorService.cause_rule_service",
            new_callable=lambda: property(lambda self: MagicMock()),
        ):
            assert svc.cause_rule_service is not None


class TestDiscountType:
    """DiscountType 测试"""

    def test_constants(self):
        from apps.cases.services.data.litigation_fee_calculator_service import DiscountType

        assert DiscountType.MEDIATION == "mediation"
        assert DiscountType.WITHDRAWAL == "withdrawal"
        assert DiscountType.SIMPLE_PROCEDURE == "simple"
        assert DiscountType.COUNTERCLAIM == "counterclaim"


class TestFeeConstants:
    """费用常量测试"""

    def test_property_case_fee_tiers(self):
        from apps.cases.services.data.litigation_fee_calculator_service import PROPERTY_CASE_FEE_TIERS

        assert len(PROPERTY_CASE_FEE_TIERS) == 10
        assert PROPERTY_CASE_FEE_TIERS[0][0] == 10000
        assert PROPERTY_CASE_FEE_TIERS[-1][0] is None

    def test_preservation_fee_tiers(self):
        from apps.cases.services.data.litigation_fee_calculator_service import PRESERVATION_FEE_TIERS

        assert len(PRESERVATION_FEE_TIERS) == 3

    def test_execution_fee_tiers(self):
        from apps.cases.services.data.litigation_fee_calculator_service import EXECUTION_FEE_TIERS

        assert len(EXECUTION_FEE_TIERS) == 5

    def test_preservation_fee_max(self):
        from apps.cases.services.data.litigation_fee_calculator_service import PRESERVATION_FEE_MAX

        assert PRESERVATION_FEE_MAX == Decimal("5000")

    def test_bankruptcy_fee_max(self):
        from apps.cases.services.data.litigation_fee_calculator_service import BANKRUPTCY_FEE_MAX

        assert BANKRUPTCY_FEE_MAX == Decimal("300000")
