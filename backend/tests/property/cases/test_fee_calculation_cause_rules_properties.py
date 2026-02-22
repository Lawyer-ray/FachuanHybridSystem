"""
费用计算案由规则属性测试

Feature: litigation-fee-cause-rules
测试基于案由规则的费用计算正确性属性

Property 4: 人格权案件分段费用计算
Property 5: 知识产权案件费用等价性
Property 6: 固定费用案件正确性
Property 7: 显示控制正确性
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.cases.services.data.cause_rule_service import (
    DEFAULT_DISPLAY_CONFIG,
    DISPLAY_CONFIG,
    FEE_RANGES,
    FIXED_FEES,
    CauseRuleService,
    SpecialCaseType,
)
from apps.cases.services.data.litigation_fee_calculator_service import (
    IP_CASE_FEE_MAX,
    IP_CASE_FEE_MIN,
    PERSONALITY_RIGHTS_FEE_MAX,
    PERSONALITY_RIGHTS_FEE_MIN,
    LitigationFeeCalculatorService,
)

# 金额策略：0 到 1000 万，保留 2 位小数
amount_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("10000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# 正数金额策略
positive_amount_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("10000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@pytest.fixture
def fee_calculator_service():
    """创建 LitigationFeeCalculatorService 实例"""
    return LitigationFeeCalculatorService()


class TestPersonalityRightsFeeWithRangeProperties:
    """人格权案件分段费用计算属性测试"""

    @settings(max_examples=100)
    @given(amount=amount_strategy)
    def test_property_4_personality_rights_tiered_fee_calculation(self, amount: Decimal):
        """
        Property 4: 人格权案件分段费用计算

        Feature: litigation-fee-cause-rules, Property 4: 人格权案件分段费用计算
        Validates: Requirements 2.3-2.5

        对于任意非负金额，人格权案件的费用计算应满足：
        - 金额 ≤ 5万：基础费用 100-500 元
        - 5万 < 金额 ≤ 10万：基础费用 + (金额 - 50000) × 1%
        - 金额 > 10万：基础费用 + 500 + (金额 - 100000) × 0.5%
        """
        service = LitigationFeeCalculatorService()
        result = service.calculate_personality_rights_fee_with_range(amount)

        base_min = PERSONALITY_RIGHTS_FEE_MIN  # 100
        base_max = PERSONALITY_RIGHTS_FEE_MAX  # 500
        threshold_1 = Decimal("50000")
        threshold_2 = Decimal("100000")

        # 验证返回结构
        assert "fee_min" in result
        assert "fee_max" in result
        assert "display_text" in result

        # 验证费用范围
        if amount <= 0:
            # 无金额或金额为0：返回基础费用范围
            assert result["fee_min"] == base_min, f"金额 {amount} 的最小费用应为 {base_min}，但得到 {result['fee_min']}"
            assert result["fee_max"] == base_max, f"金额 {amount} 的最大费用应为 {base_max}，但得到 {result['fee_max']}"
        elif amount <= threshold_1:
            # 金额 ≤ 5万：基础费用范围
            assert result["fee_min"] == base_min, f"金额 {amount} 的最小费用应为 {base_min}，但得到 {result['fee_min']}"
            assert result["fee_max"] == base_max, f"金额 {amount} 的最大费用应为 {base_max}，但得到 {result['fee_max']}"
        elif amount <= threshold_2:
            # 5万 < 金额 ≤ 10万：基础费用 + (金额 - 50000) × 1%
            extra_fee = (amount - threshold_1) * Decimal("0.01")
            expected_min = base_min + extra_fee
            expected_max = base_max + extra_fee
            assert (
                result["fee_min"] == expected_min
            ), f"金额 {amount} 的最小费用应为 {expected_min}，但得到 {result['fee_min']}"
            assert (
                result["fee_max"] == expected_max
            ), f"金额 {amount} 的最大费用应为 {expected_max}，但得到 {result['fee_max']}"
        else:
            # 金额 > 10万：基础费用 + 500 + (金额 - 100000) × 0.5%
            tier_2_fee = Decimal("500")  # (100000 - 50000) × 1%
            extra_fee = (amount - threshold_2) * Decimal("0.005")
            expected_min = base_min + tier_2_fee + extra_fee
            expected_max = base_max + tier_2_fee + extra_fee
            assert (
                result["fee_min"] == expected_min
            ), f"金额 {amount} 的最小费用应为 {expected_min}，但得到 {result['fee_min']}"
            assert (
                result["fee_max"] == expected_max
            ), f"金额 {amount} 的最大费用应为 {expected_max}，但得到 {result['fee_max']}"

    def test_personality_rights_no_amount(self, fee_calculator_service):
        """
        测试人格权案件无金额时的费用范围

        无金额时应返回基础费用范围 100-500 元。
        """
        result = fee_calculator_service.calculate_personality_rights_fee_with_range(None)

        assert result["fee"] is None
        assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN
        assert result["fee_max"] == PERSONALITY_RIGHTS_FEE_MAX
        assert "100-500元" in result["display_text"]

    def test_personality_rights_boundary_50000(self, fee_calculator_service):
        """
        测试人格权案件 5 万元边界

        金额恰好为 5 万元时应返回基础费用范围。
        """
        result = fee_calculator_service.calculate_personality_rights_fee_with_range(Decimal("50000"))

        assert result["fee_min"] == PERSONALITY_RIGHTS_FEE_MIN
        assert result["fee_max"] == PERSONALITY_RIGHTS_FEE_MAX

    def test_personality_rights_boundary_100000(self, fee_calculator_service):
        """
        测试人格权案件 10 万元边界

        金额恰好为 10 万元时应计算 5-10 万分段费用。
        """
        result = fee_calculator_service.calculate_personality_rights_fee_with_range(Decimal("100000"))

        # 5万-10万部分：50000 × 1% = 500
        extra_fee = Decimal("500")
        expected_min = PERSONALITY_RIGHTS_FEE_MIN + extra_fee
        expected_max = PERSONALITY_RIGHTS_FEE_MAX + extra_fee

        assert result["fee_min"] == expected_min
        assert result["fee_max"] == expected_max


class TestIPFeeWithRangeProperties:
    """知识产权案件费用等价性属性测试"""

    @settings(max_examples=100)
    @given(amount=positive_amount_strategy)
    def test_property_5_ip_fee_equivalence(self, amount: Decimal):
        """
        Property 5: 知识产权案件费用等价性

        Feature: litigation-fee-cause-rules, Property 5: 知识产权案件费用等价性
        Validates: Requirements 3.3

        对于任意有涉案金额的知识产权案件，其费用应等于相同金额的财产案件受理费。
        即：ip_fee(amount) = property_case_fee(amount)
        """
        service = LitigationFeeCalculatorService()

        ip_result = service.calculate_ip_fee_with_range(amount)
        property_fee = service.calculate_property_case_fee(amount)

        # 有金额时，知识产权案件费用应等于财产案件费用
        assert (
            ip_result["fee"] == property_fee
        ), f"知识产权案件费用 {ip_result['fee']} 应等于财产案件费用 {property_fee}"
        assert ip_result["fee_min"] == property_fee
        assert ip_result["fee_max"] == property_fee

    def test_ip_fee_no_amount(self, fee_calculator_service):
        """
        测试知识产权案件无金额时的费用范围

        无金额时应返回固定费用范围 500-1000 元。
        """
        result = fee_calculator_service.calculate_ip_fee_with_range(None)

        assert result["fee"] is None
        assert result["fee_min"] == IP_CASE_FEE_MIN
        assert result["fee_max"] == IP_CASE_FEE_MAX
        assert "500-1000元" in result["display_text"]

    def test_ip_fee_zero_amount(self, fee_calculator_service):
        """
        测试知识产权案件金额为 0 时的费用范围

        金额为 0 时应返回固定费用范围。
        """
        result = fee_calculator_service.calculate_ip_fee_with_range(Decimal("0"))

        assert result["fee"] is None
        assert result["fee_min"] == IP_CASE_FEE_MIN
        assert result["fee_max"] == IP_CASE_FEE_MAX


class TestFixedFeeProperties:
    """固定费用案件正确性属性测试"""

    @settings(max_examples=100)
    @given(
        case_type=st.sampled_from(
            [
                SpecialCaseType.REVOKE_ARBITRATION,
                SpecialCaseType.PUBLIC_NOTICE,
                SpecialCaseType.LABOR_DISPUTE,
            ]
        )
    )
    def test_property_6_fixed_fee_correctness(self, case_type: str):
        """
        Property 6: 固定费用案件正确性

        Feature: litigation-fee-cause-rules, Property 6: 固定费用案件正确性
        Validates: Requirements 5.2, 6.2, 7.2

        对于撤销仲裁裁决案件，费用应固定为 400 元；
        对于公示催告案件，费用应固定为 100 元；
        对于劳动争议案件，费用应固定为 10 元。
        """
        expected_fees = {
            SpecialCaseType.REVOKE_ARBITRATION: Decimal("400"),
            SpecialCaseType.PUBLIC_NOTICE: Decimal("100"),
            SpecialCaseType.LABOR_DISPUTE: Decimal("10"),
        }

        assert case_type in FIXED_FEES, f"案件类型 {case_type} 应在固定费用配置中"
        assert FIXED_FEES[case_type] == expected_fees[case_type], (
            f"案件类型 {case_type} 的固定费用应为 {expected_fees[case_type]}，" f"但配置为 {FIXED_FEES[case_type]}"
        )

    def test_revoke_arbitration_fixed_fee(self):
        """
        测试撤销仲裁裁决案件固定费用

        撤销仲裁裁决案件费用应固定为 400 元。
        """
        assert FIXED_FEES[SpecialCaseType.REVOKE_ARBITRATION] == Decimal("400")

    def test_public_notice_fixed_fee(self):
        """
        测试公示催告案件固定费用

        公示催告案件费用应固定为 100 元。
        """
        assert FIXED_FEES[SpecialCaseType.PUBLIC_NOTICE] == Decimal("100")

    def test_labor_dispute_fixed_fee(self):
        """
        测试劳动争议案件固定费用

        劳动争议案件费用应固定为 10 元。
        """
        assert FIXED_FEES[SpecialCaseType.LABOR_DISPUTE] == Decimal("10")


class TestDisplayControlProperties:
    """显示控制正确性属性测试"""

    @settings(max_examples=100)
    @given(
        case_type=st.sampled_from(
            [
                SpecialCaseType.PAYMENT_ORDER,
                SpecialCaseType.REVOKE_ARBITRATION,
                SpecialCaseType.PUBLIC_NOTICE,
                SpecialCaseType.LABOR_DISPUTE,
            ]
        )
    )
    def test_property_7_display_control_correctness(self, case_type: str):
        """
        Property 7: 显示控制正确性

        Feature: litigation-fee-cause-rules, Property 7: 显示控制正确性
        Validates: Requirements 4.2, 4.3, 5.3

        对于支付令案件，show_acceptance_fee、show_half_fee 和 show_payment_order_fee
        应全部为 True；
        对于撤销仲裁/公示催告/劳动争议案件，所有显示标志应为 False（仅显示固定费用）；
        对于普通案件，show_payment_order_fee 应为 False。
        """
        if case_type == SpecialCaseType.PAYMENT_ORDER:
            # 支付令案件：所有显示标志应为 True
            config = DISPLAY_CONFIG[case_type]
            assert config["show_acceptance_fee"] is True, "支付令案件 show_acceptance_fee 应为 True"
            assert config["show_half_fee"] is True, "支付令案件 show_half_fee 应为 True"
            assert config["show_payment_order_fee"] is True, "支付令案件 show_payment_order_fee 应为 True"
        else:
            # 撤销仲裁/公示催告/劳动争议案件：所有显示标志应为 False
            config = DISPLAY_CONFIG[case_type]
            assert config["show_acceptance_fee"] is False, f"{case_type} 案件 show_acceptance_fee 应为 False"
            assert config["show_half_fee"] is False, f"{case_type} 案件 show_half_fee 应为 False"
            assert config["show_payment_order_fee"] is False, f"{case_type} 案件 show_payment_order_fee 应为 False"

    def test_default_display_config(self):
        """
        测试默认显示配置

        普通案件的默认配置：show_payment_order_fee 应为 False。
        """
        assert DEFAULT_DISPLAY_CONFIG["show_acceptance_fee"] is True
        assert DEFAULT_DISPLAY_CONFIG["show_half_fee"] is True
        assert DEFAULT_DISPLAY_CONFIG["show_payment_order_fee"] is False

    def test_payment_order_display_config(self):
        """
        测试支付令案件显示配置

        支付令案件应显示所有费用项。
        """
        config = DISPLAY_CONFIG[SpecialCaseType.PAYMENT_ORDER]
        assert config["show_acceptance_fee"] is True
        assert config["show_half_fee"] is True
        assert config["show_payment_order_fee"] is True

    def test_fixed_fee_cases_display_config(self):
        """
        测试固定费用案件显示配置

        固定费用案件（撤销仲裁、公示催告、劳动争议）应隐藏所有常规费用项。
        """
        fixed_fee_types = [
            SpecialCaseType.REVOKE_ARBITRATION,
            SpecialCaseType.PUBLIC_NOTICE,
            SpecialCaseType.LABOR_DISPUTE,
        ]

        for case_type in fixed_fee_types:
            config = DISPLAY_CONFIG[case_type]
            assert config["show_acceptance_fee"] is False, f"{case_type} 应隐藏案件受理费"
            assert config["show_half_fee"] is False, f"{case_type} 应隐藏减半后受理费"
            assert config["show_payment_order_fee"] is False, f"{case_type} 应隐藏支付令申请费"


class TestCauseRuleFeeRuleProperties:
    """案由规则费用规则属性测试"""

    def test_fee_rule_revoke_arbitration(self):
        """
        测试撤销仲裁裁决案件费用规则

        撤销仲裁裁决案件应返回固定费用 400 元。
        """
        service = CauseRuleService() # noqa: F841

        # 模拟一个撤销仲裁案件的规则
        # 由于需要数据库中的案由，这里直接测试配置
        assert SpecialCaseType.REVOKE_ARBITRATION in FIXED_FEES
        assert FIXED_FEES[SpecialCaseType.REVOKE_ARBITRATION] == Decimal("400")

    def test_fee_rule_public_notice(self):
        """
        测试公示催告案件费用规则

        公示催告案件应返回固定费用 100 元。
        """
        assert SpecialCaseType.PUBLIC_NOTICE in FIXED_FEES
        assert FIXED_FEES[SpecialCaseType.PUBLIC_NOTICE] == Decimal("100")

    def test_fee_rule_labor_dispute(self):
        """
        测试劳动争议案件费用规则

        劳动争议案件应返回固定费用 10 元。
        """
        assert SpecialCaseType.LABOR_DISPUTE in FIXED_FEES
        assert FIXED_FEES[SpecialCaseType.LABOR_DISPUTE] == Decimal("10")

    def test_fee_range_personality_rights(self):
        """
        测试人格权案件费用范围配置

        人格权案件应配置正确的费用范围。
        """
        assert SpecialCaseType.PERSONALITY_RIGHTS in FEE_RANGES
        fee_range = FEE_RANGES[SpecialCaseType.PERSONALITY_RIGHTS]
        assert fee_range["min"] == Decimal("100")
        assert fee_range["max"] == Decimal("500")
        assert fee_range["half_min"] == Decimal("50")
        assert fee_range["half_max"] == Decimal("250")

    def test_fee_range_ip(self):
        """
        测试知识产权案件费用范围配置

        知识产权案件应配置正确的费用范围。
        """
        assert SpecialCaseType.IP in FEE_RANGES
        fee_range = FEE_RANGES[SpecialCaseType.IP]
        assert fee_range["min"] == Decimal("500")
        assert fee_range["max"] == Decimal("1000")
        assert fee_range["half_min"] == Decimal("250")
        assert fee_range["half_max"] == Decimal("500")
