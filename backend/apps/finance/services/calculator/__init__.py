"""计算模块服务.

提供各种金融计算功能，包括：
- LPR利息计算（支持固定本金和变动本金）
- 房贷摊销与逾期违约债权计算（等额本息/等额本金、罚息、复利、冲抵）
"""

from __future__ import annotations

from apps.finance.services.calculator.interest_calculator import (
    CalculationPeriod,
    InterestCalculationResult,
    InterestCalculator,
)
from apps.finance.services.calculator.mortgage_calculator import (
    AllocationDetail,
    ClaimSummary,
    DefaultRow,
    MortgageDefaultCalculator,
    MortgageDefaultResult,
    PaymentRecord,
    ScheduleRow,
)

__all__ = [
    "InterestCalculator",
    "InterestCalculationResult",
    "CalculationPeriod",
    "MortgageDefaultCalculator",
    "MortgageDefaultResult",
    "ClaimSummary",
    "DefaultRow",
    "ScheduleRow",
    "AllocationDetail",
    "PaymentRecord",
]
