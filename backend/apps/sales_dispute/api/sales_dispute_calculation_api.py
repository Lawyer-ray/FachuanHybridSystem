"""买卖纠纷计算 API — 利息/费用/LPR/时效计算端点。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.sales_dispute.schemas import (
    CostBenefitRequest,
    CostBenefitResponse,
    InterestCalcRequest,
    InterestCalcResponse,
    LPRRateResponse,
    LimitationRequest,
    LimitationResponse,
    SegmentDetailResponse,
)

from .sales_dispute_api_factories import (
    _get_cost_benefit_service,
    _get_interest_calculator,
    _get_lpr_rate_service,
    _get_limitation_calculator,
)

router = Router()


@router.post("/calculate-interest", response=InterestCalcResponse)
def calculate_interest(
    request: HttpRequest,
    data: InterestCalcRequest,
) -> InterestCalcResponse:
    """利息/违约金计算"""
    from apps.sales_dispute.services.interest_calculator_service import (
        BatchDelivery,
        InterestCalcParams,
        InterestStartType,
        RateType,
    )

    batch_deliveries: list[BatchDelivery] | None = None
    if data.batch_deliveries:
        batch_deliveries = [
            BatchDelivery(
                delivery_date=item.delivery_date,
                amount=Decimal(str(item.amount)),
                payment_date=item.payment_date,
            )
            for item in data.batch_deliveries
        ]

    params = InterestCalcParams(
        principal=Decimal(str(data.principal)),
        start_date=data.start_date,
        end_date=data.end_date,
        rate_type=RateType(data.rate_type),
        agreed_rate=Decimal(str(data.agreed_rate)) if data.agreed_rate is not None else None,
        penalty_amount=Decimal(str(data.penalty_amount)) if data.penalty_amount is not None else None,
        penalty_daily_rate=Decimal(str(data.penalty_daily_rate)) if data.penalty_daily_rate is not None else None,
        lpr_markup=Decimal(str(data.lpr_markup)),
        interest_start_type=InterestStartType(data.interest_start_type),
        agreed_payment_date=data.agreed_payment_date,
        demand_date=data.demand_date,
        reasonable_period_days=data.reasonable_period_days,
        batch_deliveries=batch_deliveries,
    )

    svc = _get_interest_calculator()
    result = svc.calculate(params)

    segments = [
        SegmentDetailResponse(
            start_date=seg.start_date,
            end_date=seg.end_date,
            days=seg.days,
            rate=float(seg.rate),
            interest=float(seg.interest),
        )
        for seg in result.segments
    ]

    return InterestCalcResponse(
        total_interest=float(result.total_interest),
        segments=segments,
        warnings=result.warnings,
    )


@router.post("/calculate-cost", response=CostBenefitResponse)
def calculate_cost(
    request: HttpRequest,
    data: CostBenefitRequest,
) -> CostBenefitResponse:
    """成本收益分析"""
    from apps.sales_dispute.services.cost_benefit_service import CostBenefitParams

    params = CostBenefitParams(
        principal=Decimal(str(data.principal)),
        interest_amount=Decimal(str(data.interest_amount)),
        lawyer_fee=Decimal(str(data.lawyer_fee)),
        preservation_amount=Decimal(str(data.preservation_amount)),
        guarantee_rate=Decimal(str(data.guarantee_rate)),
        notary_fee=Decimal(str(data.notary_fee)),
        case_type=data.case_type,
        cause_of_action=data.cause_of_action,
        recovery_rate=Decimal(str(data.recovery_rate)),
        support_rate=Decimal(str(data.support_rate)),
        fee_transfer_rate=Decimal(str(data.fee_transfer_rate)),
        lawyer_transfer_rate=Decimal(str(data.lawyer_transfer_rate)),
    )

    svc = _get_cost_benefit_service()
    result = svc.analyze(params)

    return CostBenefitResponse(
        total_cost=float(result.total_cost),
        total_revenue=float(result.total_revenue),
        net_profit=float(result.net_profit),
        roi=float(result.roi),
        cost_details={k: float(v) for k, v in result.cost_details.items()},
        revenue_details={k: float(v) for k, v in result.revenue_details.items()},
        risk_warning=result.risk_warning,
    )


@router.get("/lpr-rates", response=list[LPRRateResponse])
def list_lpr_rates(request: HttpRequest) -> list[LPRRateResponse]:
    """获取LPR利率历史数据"""
    svc = _get_lpr_rate_service()
    rates = svc.get_all_rates()

    return [
        LPRRateResponse(
            effective_date=rate.effective_date,
            rate_1y=float(rate.rate_1y),
            rate_5y=float(rate.rate_5y),
        )
        for rate in rates
    ]


@router.post("/calculate-limitation", response=LimitationResponse)
def calculate_limitation(
    request: HttpRequest,
    data: LimitationRequest,
) -> LimitationResponse:
    """诉讼时效计算"""
    from apps.sales_dispute.services.limitation_calculator_service import (
        InterruptionEvent,
        InterruptionType,
        LimitationCalcParams,
    )

    interruptions = [
        InterruptionEvent(
            event_type=InterruptionType(evt.event_type),
            event_date=evt.event_date,
        )
        for evt in data.interruptions
    ]

    params = LimitationCalcParams(
        last_claim_date=data.last_claim_date,
        interruptions=interruptions,
        guarantee_debtor=data.guarantee_debtor,
        principal_due_date=data.principal_due_date,
    )

    svc = _get_limitation_calculator()
    result = svc.calculate(params)

    return LimitationResponse(
        status=result.status,
        expiry_date=result.expiry_date,
        remaining_days=result.remaining_days,
        base_date=result.base_date,
        risk_warning=result.risk_warning,
        guarantee_expiry_date=result.guarantee_expiry_date,
    )
