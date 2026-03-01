"""
Sales Dispute Services 模块
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "LprRateService",
    "RateSegment",
    "InterestCalculatorService",
    "InterestStartType",
    "RateType",
    "InterestCalcParams",
    "InterestCalcResult",
    "BatchDelivery",
    "SegmentDetail",
    "RepaymentOffsetService",
    "DebtItem",
    "OffsetDetail",
    "OffsetResult",
    "PaymentInput",
    "CostBenefitService",
    "CostBenefitParams",
    "CostBenefitResult",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "LprRateService": (
        "apps.sales_dispute.services.lpr_rate_service",
        "LprRateService",
    ),
    "RateSegment": (
        "apps.sales_dispute.services.lpr_rate_service",
        "RateSegment",
    ),
    "InterestCalculatorService": (
        "apps.sales_dispute.services.interest_calculator_service",
        "InterestCalculatorService",
    ),
    "InterestStartType": (
        "apps.sales_dispute.services.interest_calculator_service",
        "InterestStartType",
    ),
    "RateType": (
        "apps.sales_dispute.services.interest_calculator_service",
        "RateType",
    ),
    "InterestCalcParams": (
        "apps.sales_dispute.services.interest_calculator_service",
        "InterestCalcParams",
    ),
    "InterestCalcResult": (
        "apps.sales_dispute.services.interest_calculator_service",
        "InterestCalcResult",
    ),
    "BatchDelivery": (
        "apps.sales_dispute.services.interest_calculator_service",
        "BatchDelivery",
    ),
    "SegmentDetail": (
        "apps.sales_dispute.services.interest_calculator_service",
        "SegmentDetail",
    ),
    "RepaymentOffsetService": (
        "apps.sales_dispute.services.repayment_offset_service",
        "RepaymentOffsetService",
    ),
    "DebtItem": (
        "apps.sales_dispute.services.repayment_offset_service",
        "DebtItem",
    ),
    "OffsetDetail": (
        "apps.sales_dispute.services.repayment_offset_service",
        "OffsetDetail",
    ),
    "OffsetResult": (
        "apps.sales_dispute.services.repayment_offset_service",
        "OffsetResult",
    ),
    "PaymentInput": (
        "apps.sales_dispute.services.repayment_offset_service",
        "PaymentInput",
    ),
    "CostBenefitService": (
        "apps.sales_dispute.services.cost_benefit_service",
        "CostBenefitService",
    ),
    "CostBenefitParams": (
        "apps.sales_dispute.services.cost_benefit_service",
        "CostBenefitParams",
    ),
    "CostBenefitResult": (
        "apps.sales_dispute.services.cost_benefit_service",
        "CostBenefitResult",
    ),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__) | set(_LAZY_EXPORTS.keys()))
