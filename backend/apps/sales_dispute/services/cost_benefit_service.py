"""
成本收益分析器

综合计算诉讼成本和预期收益，输出净收益、投入产出比及风险提示。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.cases.services.data.litigation_fee_calculator_service import (
        LitigationFeeCalculatorService,
    )

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_TWO_PLACES = Decimal("0.01")

# 默认费率常量
DEFAULT_RATES: dict[str, Decimal] = {
    "principal_recovery_rate": Decimal("0.70"),
    "interest_support_rate": Decimal("0.85"),
    "litigation_fee_transfer_rate": Decimal("0.95"),
    "lawyer_fee_transfer_rate": Decimal("0.60"),
}


@dataclass
class CostBenefitParams:
    """成本收益分析参数"""

    principal: Decimal
    interest_amount: Decimal
    lawyer_fee: Decimal = _ZERO
    preservation_amount: Decimal = _ZERO
    guarantee_rate: Decimal = Decimal("0.015")
    notary_fee: Decimal = _ZERO
    case_type: str | None = None
    cause_of_action: str | None = None
    recovery_rate: Decimal = field(
        default_factory=lambda: DEFAULT_RATES["principal_recovery_rate"]
    )
    support_rate: Decimal = field(
        default_factory=lambda: DEFAULT_RATES["interest_support_rate"]
    )
    fee_transfer_rate: Decimal = field(
        default_factory=lambda: DEFAULT_RATES["litigation_fee_transfer_rate"]
    )
    lawyer_transfer_rate: Decimal = field(
        default_factory=lambda: DEFAULT_RATES["lawyer_fee_transfer_rate"]
    )


@dataclass
class CostBenefitResult:
    """成本收益分析结果"""

    total_cost: Decimal
    total_revenue: Decimal
    net_profit: Decimal
    roi: Decimal
    cost_details: dict[str, Decimal]
    revenue_details: dict[str, Decimal]
    risk_warning: str | None = None


class CostBenefitService:
    """成本收益分析服务"""

    def __init__(
        self, fee_calculator: LitigationFeeCalculatorService | None = None
    ) -> None:
        self._fee_calculator = fee_calculator

    def _get_fee_calculator(self) -> LitigationFeeCalculatorService:
        """延迟获取 LitigationFeeCalculatorService 实例"""
        if self._fee_calculator is None:
            from apps.cases.services.data.litigation_fee_calculator_service import (
                LitigationFeeCalculatorService,
            )

            self._fee_calculator = LitigationFeeCalculatorService()
        return self._fee_calculator

    def analyze(self, params: CostBenefitParams) -> CostBenefitResult:
        """
        成本收益分析

        计算流程：
        1. 成本 = 律师费 + 诉讼费 + 保全费 + 担保费 + 公证费
        2. 收益 = 本金×回收率 + 利息×支持率 + 诉讼费×转嫁率 + 律师费×转嫁率
        3. 净收益 = 收益 - 成本
        4. 投入产出比 = 收益 / 成本
        5. 净收益 < 0 时标注风险提示
        """
        calculator = self._get_fee_calculator()

        # --- 成本计算 ---
        claim_amount = params.principal + params.interest_amount
        litigation_fee = calculator.calculate_property_case_fee(claim_amount)

        preservation_fee = _ZERO
        if params.preservation_amount > _ZERO:
            preservation_fee = calculator.calculate_preservation_fee(
                params.preservation_amount
            )

        guarantee_fee = (
            params.preservation_amount * params.guarantee_rate
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        total_cost = (
            params.lawyer_fee
            + litigation_fee
            + preservation_fee
            + guarantee_fee
            + params.notary_fee
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        cost_details: dict[str, Decimal] = {
            "lawyer_fee": params.lawyer_fee.quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            ),
            "litigation_fee": litigation_fee.quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            ),
            "preservation_fee": preservation_fee.quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            ),
            "guarantee_fee": guarantee_fee,
            "notary_fee": params.notary_fee.quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            ),
        }

        # --- 收益计算 ---
        revenue_principal = (
            params.principal * params.recovery_rate
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        revenue_interest = (
            params.interest_amount * params.support_rate
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        revenue_litigation_fee = (
            litigation_fee * params.fee_transfer_rate
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        revenue_lawyer_fee = (
            params.lawyer_fee * params.lawyer_transfer_rate
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        total_revenue = (
            revenue_principal
            + revenue_interest
            + revenue_litigation_fee
            + revenue_lawyer_fee
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        revenue_details: dict[str, Decimal] = {
            "principal": revenue_principal,
            "interest": revenue_interest,
            "litigation_fee": revenue_litigation_fee,
            "lawyer_fee": revenue_lawyer_fee,
        }

        # --- 净收益 & 投入产出比 ---
        net_profit = (total_revenue - total_cost).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        roi = _ZERO
        if total_cost > _ZERO:
            roi = (total_revenue / total_cost).quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            )

        # --- 风险提示 ---
        risk_warning: str | None = None
        if net_profit < _ZERO:
            risk_warning = str(
                _("净收益为负，诉讼经济效益较低，建议谨慎评估")
            )

        logger.info(
            "成本收益分析: cost=%s revenue=%s net=%s roi=%s",
            total_cost,
            total_revenue,
            net_profit,
            roi,
        )

        return CostBenefitResult(
            total_cost=total_cost,
            total_revenue=total_revenue,
            net_profit=net_profit,
            roi=roi,
            cost_details=cost_details,
            revenue_details=revenue_details,
            risk_warning=risk_warning,
        )
