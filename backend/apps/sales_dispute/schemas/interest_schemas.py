"""
买卖纠纷计算 Schema 定义

API 层的请求/响应数据结构，使用 float 类型。
在 API 边界层与 Service 层的 Decimal 类型互转。
"""

from __future__ import annotations

from datetime import date

from ninja import Schema


class BatchDeliveryItem(Schema):
    """分批交货条目"""

    delivery_date: date
    amount: float
    payment_date: date | None = None


class InterestCalcRequest(Schema):
    """利息计算请求"""

    principal: float
    start_date: date
    end_date: date
    rate_type: str = "lpr"
    agreed_rate: float | None = None
    penalty_amount: float | None = None
    penalty_daily_rate: float | None = None
    lpr_markup: float = 0.0
    interest_start_type: str = "agreed_date"
    agreed_payment_date: date | None = None
    demand_date: date | None = None
    reasonable_period_days: int = 30
    batch_deliveries: list[BatchDeliveryItem] | None = None


class SegmentDetailResponse(Schema):
    """利息分段明细"""

    start_date: date
    end_date: date
    days: int
    rate: float
    interest: float


class InterestCalcResponse(Schema):
    """利息计算响应"""

    total_interest: float
    segments: list[SegmentDetailResponse]
    warnings: list[str]


class CostBenefitRequest(Schema):
    """成本收益分析请求"""

    principal: float
    interest_amount: float
    lawyer_fee: float = 0
    preservation_amount: float = 0
    guarantee_rate: float = 0.015
    notary_fee: float = 0
    case_type: str | None = None
    cause_of_action: str | None = None
    recovery_rate: float = 0.70
    support_rate: float = 0.85
    fee_transfer_rate: float = 0.95
    lawyer_transfer_rate: float = 0.60


class CostBenefitResponse(Schema):
    """成本收益分析响应"""

    total_cost: float
    total_revenue: float
    net_profit: float
    roi: float
    cost_details: dict[str, float]
    revenue_details: dict[str, float]
    risk_warning: str | None = None


class LPRRateResponse(Schema):
    """LPR利率响应"""

    effective_date: date
    rate_1y: float
    rate_5y: float
