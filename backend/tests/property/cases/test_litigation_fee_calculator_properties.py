"""
诉讼费用计算器属性测试

Feature: litigation-fee-calculator
测试费用计算的正确性属性
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.cases.services.data.litigation_fee_calculator_service import (
    BANKRUPTCY_FEE_MAX,
    PRESERVATION_FEE_MAX,
    PROPERTY_CASE_FEE_TIERS,
    DiscountType,
    LitigationFeeCalculatorService,
)

# 金额策略：0 到 1 亿，保留 2 位小数
amount_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# 正数金额策略
positive_amount_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("100000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def manual_calculate_property_case_fee(amount: Decimal) -> Decimal:
    """手动计算财产案件受理费，用于验证"""
    if amount <= 0:
        return Decimal("50")
    if amount <= 10000:
        return Decimal("50")
    if amount <= 100000:
        return Decimal("50") + (amount - Decimal("10000")) * Decimal("0.025")
    if amount <= 200000:
        return Decimal("2300") + (amount - Decimal("100000")) * Decimal("0.02")
    if amount <= 500000:
        return Decimal("4300") + (amount - Decimal("200000")) * Decimal("0.015")
    if amount <= 1000000:
        return Decimal("8800") + (amount - Decimal("500000")) * Decimal("0.01")
    if amount <= 2000000:
        return Decimal("13800") + (amount - Decimal("1000000")) * Decimal("0.009")
    if amount <= 5000000:
        return Decimal("22800") + (amount - Decimal("2000000")) * Decimal("0.008")
    if amount <= 10000000:
        return Decimal("46800") + (amount - Decimal("5000000")) * Decimal("0.007")
    if amount <= 20000000:
        return Decimal("81800") + (amount - Decimal("10000000")) * Decimal("0.006")
    return Decimal("141800") + (amount - Decimal("20000000")) * Decimal("0.005")


class TestPropertyCaseFeeProperties:
    """财产案件受理费属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_1_tiered_calculation_correctness(self, amount: Decimal):
        """
        Property 1: 分段累计计算正确性

        Feature: litigation-fee-calculator, Property 1: 分段累计计算正确性
        Validates: Requirements 1.1, 1.2-1.11

        对于任意非负金额，财产案件受理费的计算结果应等于按照分段累计规则手动计算的结果。
        """
        service = LitigationFeeCalculatorService()
        calculated_fee = service.calculate_property_case_fee(amount)
        expected_fee = manual_calculate_property_case_fee(amount)

        assert calculated_fee == expected_fee, f"金额 {amount} 的计算结果 {calculated_fee} 与预期 {expected_fee} 不符"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_case_fee_non_negative(self, amount: Decimal):
        """
        Property: 财产案件受理费非负

        对于任意非负金额，计算结果应为非负数。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_property_case_fee(amount)
        assert fee >= 0, f"费用不应为负数，但得到 {fee}"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_case_fee_minimum(self, amount: Decimal):
        """
        Property: 财产案件受理费最低 50 元

        对于任意非负金额，计算结果应至少为 50 元。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_property_case_fee(amount)
        assert fee >= Decimal("50"), f"费用应至少为 50 元，但得到 {fee}"

    @settings(max_examples=100)
    @given(
        amount1=amount_strategy,
        amount2=amount_strategy,
    )
    def test_property_case_fee_monotonic(self, amount1: Decimal, amount2: Decimal):
        """
        Property: 财产案件受理费单调递增

        对于任意两个金额，较大金额的费用应不小于较小金额的费用。
        """
        service = LitigationFeeCalculatorService()
        fee1 = service.calculate_property_case_fee(amount1)
        fee2 = service.calculate_property_case_fee(amount2)

        if amount1 <= amount2:
            assert fee1 <= fee2, f"金额 {amount1} 的费用 {fee1} 应不大于金额 {amount2} 的费用 {fee2}"
        else:
            assert fee1 >= fee2, f"金额 {amount1} 的费用 {fee1} 应不小于金额 {amount2} 的费用 {fee2}"


class TestPreservationFeeProperties:
    """财产保全费属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_2_preservation_fee_max_limit(self, amount: Decimal):
        """
        Property 2: 财产保全费上限约束

        Feature: litigation-fee-calculator, Property 2: 财产保全费上限约束
        Validates: Requirements 2.4

        对于任意非负金额，财产保全申请费的计算结果不应超过5000元。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_preservation_fee(amount)

        assert fee <= PRESERVATION_FEE_MAX, f"财产保全费 {fee} 超过上限 {PRESERVATION_FEE_MAX}"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_preservation_fee_minimum(self, amount: Decimal):
        """
        Property: 财产保全费最低 30 元

        对于任意非负金额，计算结果应至少为 30 元。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_preservation_fee(amount)
        assert fee >= Decimal("30"), f"费用应至少为 30 元，但得到 {fee}"

    @settings(max_examples=100)
    @given(
        amount1=amount_strategy,
        amount2=amount_strategy,
    )
    def test_preservation_fee_monotonic(self, amount1: Decimal, amount2: Decimal):
        """
        Property: 财产保全费单调递增（在上限内）

        对于任意两个金额，较大金额的费用应不小于较小金额的费用。
        """
        service = LitigationFeeCalculatorService()
        fee1 = service.calculate_preservation_fee(amount1)
        fee2 = service.calculate_preservation_fee(amount2)

        if amount1 <= amount2:
            assert fee1 <= fee2, f"金额 {amount1} 的费用 {fee1} 应不大于金额 {amount2} 的费用 {fee2}"


def manual_calculate_execution_fee(amount: Decimal) -> Decimal:
    """手动计算执行案件费用，用于验证"""
    if amount <= 0:
        return Decimal("50")
    if amount <= 10000:
        return Decimal("50")
    if amount <= 500000:
        return Decimal("50") + (amount - Decimal("10000")) * Decimal("0.015")
    if amount <= 5000000:
        return Decimal("7400") + (amount - Decimal("500000")) * Decimal("0.01")
    if amount <= 10000000:
        return Decimal("52400") + (amount - Decimal("5000000")) * Decimal("0.005")
    return Decimal("77400") + (amount - Decimal("10000000")) * Decimal("0.001")


class TestExecutionFeeProperties:
    """执行案件费属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_3_execution_fee_tiered_calculation(self, amount: Decimal):
        """
        Property 3: 执行案件费分段累计正确性

        Feature: litigation-fee-calculator, Property 3: 执行案件费分段累计正确性
        Validates: Requirements 3.1-3.5

        对于任意非负金额，执行案件费用的计算结果应等于按照执行费分段累计规则计算的结果。
        """
        service = LitigationFeeCalculatorService()
        calculated_fee = service.calculate_execution_fee(amount)
        expected_fee = manual_calculate_execution_fee(amount)

        assert calculated_fee == expected_fee, f"金额 {amount} 的计算结果 {calculated_fee} 与预期 {expected_fee} 不符"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_execution_fee_minimum(self, amount: Decimal):
        """
        Property: 执行案件费最低 50 元

        对于任意非负金额，计算结果应至少为 50 元。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_execution_fee(amount)
        assert fee >= Decimal("50"), f"费用应至少为 50 元，但得到 {fee}"

    @settings(max_examples=100)
    @given(
        amount1=amount_strategy,
        amount2=amount_strategy,
    )
    def test_execution_fee_monotonic(self, amount1: Decimal, amount2: Decimal):
        """
        Property: 执行案件费单调递增

        对于任意两个金额，较大金额的费用应不小于较小金额的费用。
        """
        service = LitigationFeeCalculatorService()
        fee1 = service.calculate_execution_fee(amount1)
        fee2 = service.calculate_execution_fee(amount2)

        if amount1 <= amount2:
            assert fee1 <= fee2, f"金额 {amount1} 的费用 {fee1} 应不大于金额 {amount2} 的费用 {fee2}"


class TestPaymentOrderFeeProperties:
    """支付令申请费属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_4_payment_order_fee_transformation(self, amount: Decimal):
        """
        Property 4: 支付令费用变换关系

        Feature: litigation-fee-calculator, Property 4: 支付令费用变换关系
        Validates: Requirements 4.1, 4.2

        对于任意非负金额 A，支付令申请费应等于财产案件受理费除以3。
        即：payment_order_fee(A) = property_case_fee(A) / 3
        """
        service = LitigationFeeCalculatorService()
        property_fee = service.calculate_property_case_fee(amount)
        payment_order_fee = service.calculate_payment_order_fee(amount)

        expected_fee = property_fee / Decimal("3")

        assert (
            payment_order_fee == expected_fee
        ), f"支付令费用 {payment_order_fee} 应等于财产案件费用 {property_fee} / 3 = {expected_fee}"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_payment_order_fee_non_negative(self, amount: Decimal):
        """
        Property: 支付令申请费非负

        对于任意非负金额，计算结果应为非负数。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_payment_order_fee(amount)
        assert fee >= 0, f"费用不应为负数，但得到 {fee}"


from apps.cases.services.data.litigation_fee_calculator_service import (
    BANKRUPTCY_FEE_MAX,
    DIVORCE_PROPERTY_RATE,
    DIVORCE_PROPERTY_THRESHOLD,
    IP_CASE_FEE_DEFAULT,
)


class TestIPCaseFeeProperties:
    """知识产权案件费属性测试"""

    @settings(max_examples=100)
    @given(amount=positive_amount_strategy)
    def test_property_5_ip_case_fee_equivalence(self, amount: Decimal):
        """
        Property 5: 知识产权案件费用等价性

        Feature: litigation-fee-calculator, Property 5: 知识产权案件费用等价性
        Validates: Requirements 5.2

        对于任意有争议金额的知识产权案件，其费用应等于相同金额的财产案件受理费。
        """
        service = LitigationFeeCalculatorService()
        ip_fee = service.calculate_ip_case_fee(amount)
        property_fee = service.calculate_property_case_fee(amount)

        assert ip_fee == property_fee, f"知识产权案件费用 {ip_fee} 应等于财产案件费用 {property_fee}"

    def test_ip_case_fee_no_amount(self):
        """
        Property: 无争议金额时返回固定费用

        当知识产权案件没有争议金额时，应返回固定费用。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_ip_case_fee(None)
        assert fee == IP_CASE_FEE_DEFAULT


class TestDivorceCaseFeeProperties:
    """离婚案件费属性测试"""

    @settings(max_examples=100)
    @given(
        property_amount=st.decimals(
            min_value=Decimal("200001"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_property_6_divorce_case_property_fee(self, property_amount: Decimal):
        """
        Property 6: 离婚案件财产分割费用计算

        Feature: litigation-fee-calculator, Property 6: 离婚案件财产分割费用计算
        Validates: Requirements 6.3

        对于财产总额超过20万元的离婚案件，额外费用应等于 (财产总额 - 200000) × 0.005。
        """
        service = LitigationFeeCalculatorService()
        base_fee = Decimal("200")  # 使用中间值
        total_fee = service.calculate_divorce_case_fee(base_fee, property_amount)

        expected_extra = (property_amount - DIVORCE_PROPERTY_THRESHOLD) * DIVORCE_PROPERTY_RATE
        expected_total = base_fee + expected_extra

        assert total_fee == expected_total, f"离婚案件费用 {total_fee} 应等于 {expected_total}"

    @settings(max_examples=100)
    @given(
        property_amount=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("200000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_divorce_case_no_extra_fee_under_threshold(self, property_amount: Decimal):
        """
        Property: 财产不超过20万时不收额外费用

        当离婚案件财产总额不超过20万元时，不应收取额外费用。
        """
        service = LitigationFeeCalculatorService()
        base_fee = Decimal("200")
        total_fee = service.calculate_divorce_case_fee(base_fee, property_amount)

        assert (
            total_fee == base_fee
        ), f"财产 {property_amount} 不超过20万，费用应为基础费用 {base_fee}，但得到 {total_fee}"


class TestPersonalityRightsFeeProperties:
    """人格权案件费属性测试"""

    @settings(max_examples=100)
    @given(
        damage_amount=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_property_7_personality_rights_tiered_calculation(self, damage_amount: Decimal):
        """
        Property 7: 人格权案件分段计算正确性

        Feature: litigation-fee-calculator, Property 7: 人格权案件分段计算正确性
        Validates: Requirements 7.2-7.4

        对于涉及损害赔偿的人格权案件，额外费用应按照分段规则正确计算：
        5万以下不收费，5-10万按1%，10万以上按0.5%。
        """
        service = LitigationFeeCalculatorService()
        base_fee = Decimal("300")  # 使用中间值
        total_fee = service.calculate_personality_rights_fee(base_fee, damage_amount)

        # 手动计算预期额外费用
        if damage_amount <= 50000:
            expected_extra = Decimal("0")
        elif damage_amount <= 100000:
            expected_extra = (damage_amount - Decimal("50000")) * Decimal("0.01")
        else:
            expected_extra = Decimal("500") + (damage_amount - Decimal("100000")) * Decimal("0.005")

        expected_total = base_fee + expected_extra

        assert total_fee == expected_total, f"人格权案件费用 {total_fee} 应等于 {expected_total}"


class TestBankruptcyFeeProperties:
    """破产案件费属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_8_bankruptcy_fee_transformation(self, amount: Decimal):
        """
        Property 8: 破产案件费用变换关系

        Feature: litigation-fee-calculator, Property 8: 破产案件费用变换关系
        Validates: Requirements 8.1

        对于任意非负金额 A，破产案件费用应等于财产案件受理费的一半。
        即：bankruptcy_fee(A) = property_case_fee(A) / 2
        """
        service = LitigationFeeCalculatorService()
        property_fee = service.calculate_property_case_fee(amount)
        bankruptcy_fee = service.calculate_bankruptcy_fee(amount)

        expected_fee = min(property_fee / Decimal("2"), BANKRUPTCY_FEE_MAX)

        assert bankruptcy_fee == expected_fee, f"破产案件费用 {bankruptcy_fee} 应等于 {expected_fee}"

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_9_bankruptcy_fee_max_limit(self, amount: Decimal):
        """
        Property 9: 破产案件费用上限约束

        Feature: litigation-fee-calculator, Property 9: 破产案件费用上限约束
        Validates: Requirements 8.2

        对于任意非负金额，破产案件费用不应超过30万元。
        """
        service = LitigationFeeCalculatorService()
        fee = service.calculate_bankruptcy_fee(amount)

        assert fee <= BANKRUPTCY_FEE_MAX, f"破产案件费用 {fee} 超过上限 {BANKRUPTCY_FEE_MAX}"


class TestDiscountProperties:
    """费用减免属性测试"""

    @settings(max_examples=100)
    @given(
        fee=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        discount_type=st.sampled_from(
            [
                DiscountType.MEDIATION,
                DiscountType.WITHDRAWAL,
                DiscountType.SIMPLE_PROCEDURE,
                DiscountType.COUNTERCLAIM,
            ]
        ),
    )
    def test_property_10_discount_transformation(self, fee: Decimal, discount_type: str):
        """
        Property 10: 费用减免变换关系

        Feature: litigation-fee-calculator, Property 10: 费用减免变换关系
        Validates: Requirements 9.1, 9.2, 9.3

        对于任意原始费用 F 和减免类型（调解/撤诉/简易程序/反诉合并），
        减免后费用应等于 F / 2。
        """
        service = LitigationFeeCalculatorService()
        discounted_fee = service.apply_discount(fee, discount_type)

        expected_fee = fee / Decimal("2")

        assert discounted_fee == expected_fee, f"减免后费用 {discounted_fee} 应等于原始费用 {fee} / 2 = {expected_fee}"

    @settings(max_examples=100)
    @given(
        fee=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_discount_invalid_type_no_change(self, fee: Decimal):
        """
        Property: 无效减免类型不改变费用

        对于无效的减免类型，费用应保持不变。
        """
        service = LitigationFeeCalculatorService()
        discounted_fee = service.apply_discount(fee, "invalid_type")

        assert discounted_fee == fee, f"无效减免类型应返回原始费用 {fee}，但得到 {discounted_fee}"


class TestAPIProperties:
    """API 属性测试"""

    @settings(max_examples=100)
    @given(
        target_amount=st.one_of(
            st.none(),
            st.floats(min_value=0, max_value=100000000, allow_nan=False, allow_infinity=False),
        ),
        preservation_amount=st.one_of(
            st.none(),
            st.floats(min_value=0, max_value=100000000, allow_nan=False, allow_infinity=False),
        ),
    )
    def test_property_11_api_response_format_consistency(
        self,
        target_amount,
        preservation_amount,
    ):
        """
        Property 11: API响应格式一致性

        Feature: litigation-fee-calculator, Property 11: API响应格式一致性
        Validates: Requirements 10.2

        对于任意有效的计算请求，API响应应包含所有必需的费用字段，且数值类型正确。
        """
        service = LitigationFeeCalculatorService()

        target = Decimal(str(target_amount)) if target_amount is not None else None
        preservation = Decimal(str(preservation_amount)) if preservation_amount is not None else None

        result = service.calculate_all_fees(
            target_amount=target,
            preservation_amount=preservation,
            case_type=None,
            cause_of_action=None,
        )

        # 验证响应包含所有必需字段
        assert "acceptance_fee" in result
        assert "acceptance_fee_half" in result
        assert "preservation_fee" in result
        assert "execution_fee" in result
        assert "payment_order_fee" in result
        assert "bankruptcy_fee" in result
        assert "calculation_details" in result

        # 验证数值类型正确
        for key in [
            "acceptance_fee",
            "acceptance_fee_half",
            "preservation_fee",
            "execution_fee",
            "payment_order_fee",
            "bankruptcy_fee",
        ]:
            value = result[key]
            assert value is None or isinstance(
                value, (int, float)
            ), f"字段 {key} 应为 None 或数值类型，但得到 {type(value)}"

        assert isinstance(result["calculation_details"], list)

    def test_property_12_api_input_validation_negative_target(self):
        """
        Property 12: API输入验证 - 负数涉案金额

        Feature: litigation-fee-calculator, Property 12: API输入验证
        Validates: Requirements 10.3

        对于负数输入，API应返回验证错误而非计算结果。
        """
        from apps.cases.api.litigation_fee_api import FeeCalculationRequest, calculate_fee
        from apps.core.exceptions import ValidationException

        # 创建带负数的请求
        data = FeeCalculationRequest(target_amount=-100)

        # 应该抛出验证异常
        try:
            calculate_fee(None, data)  # type: ignore[arg-type]
            assert False, "应该抛出 ValidationException"
        except ValidationException as e:
            assert "负数" in str(e) or "不能" in str(e)

    def test_property_12_api_input_validation_negative_preservation(self):
        """
        Property 12: API输入验证 - 负数保全金额

        Feature: litigation-fee-calculator, Property 12: API输入验证
        Validates: Requirements 10.3

        对于负数输入，API应返回验证错误而非计算结果。
        """
        from apps.cases.api.litigation_fee_api import FeeCalculationRequest, calculate_fee
        from apps.core.exceptions import ValidationException

        # 创建带负数的请求
        data = FeeCalculationRequest(preservation_amount=-100)

        # 应该抛出验证异常
        try:
            calculate_fee(None, data)  # type: ignore[arg-type]
            assert False, "应该抛出 ValidationException"
        except ValidationException as e:
            assert "负数" in str(e) or "不能" in str(e)
