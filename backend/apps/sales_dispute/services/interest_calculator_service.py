"""
利息分段计算引擎

根据LPR利率历史数据和合同条件计算逾期利息/违约金
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.sales_dispute.services.lpr_rate_service import LprRateService

logger = logging.getLogger(__name__)

# LPR分水岭日期：2019年8月20日
LPR_WATERSHED = date(2019, 8, 20)

# 2019.8.20之前的一年期贷款基准利率
OLD_BENCHMARK_RATE_1Y = Decimal("4.35")

# Decimal 常量
_ZERO = Decimal("0")
_DAYS_PER_YEAR = Decimal("365")
_BASIS_POINTS = Decimal("10000")
_HUNDRED = Decimal("100")
_TWO_PLACES = Decimal("0.01")


class InterestStartType(str, Enum):
    """计息起算日类型"""

    AGREED_DATE = "agreed_date"
    DEMAND_NOTICE = "demand_notice"
    BATCH_DELIVERY = "batch_delivery"


class RateType(str, Enum):
    """利率类型"""

    LPR = "lpr"
    AGREED_RATE = "agreed_rate"
    PENALTY_FIXED = "penalty_fixed"
    PENALTY_DAILY = "penalty_daily"


@dataclass
class BatchDelivery:
    """分批交货记录"""

    delivery_date: date
    amount: Decimal
    payment_date: date | None = None


@dataclass
class SegmentDetail:
    """利息分段明细"""

    start_date: date
    end_date: date
    days: int
    rate: Decimal
    interest: Decimal


@dataclass
class InterestCalcParams:
    """利息计算参数"""

    principal: Decimal
    start_date: date
    end_date: date
    rate_type: RateType = RateType.LPR
    agreed_rate: Decimal | None = None
    penalty_amount: Decimal | None = None
    penalty_daily_rate: Decimal | None = None
    lpr_markup: Decimal = _ZERO
    interest_start_type: InterestStartType = InterestStartType.AGREED_DATE
    agreed_payment_date: date | None = None
    demand_date: date | None = None
    reasonable_period_days: int = 30
    batch_deliveries: list[BatchDelivery] | None = None


@dataclass
class InterestCalcResult:
    """利息计算结果"""

    total_interest: Decimal = _ZERO
    segments: list[SegmentDetail] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class InterestCalculatorService:
    """利息分段计算引擎"""

    def __init__(self, lpr_rate_service: LprRateService | None = None) -> None:
        self._lpr_rate_service = lpr_rate_service

    def _get_lpr_service(self) -> LprRateService:
        """延迟获取 LprRateService 实例"""
        if self._lpr_rate_service is None:
            from apps.sales_dispute.services.lpr_rate_service import LprRateService

            self._lpr_rate_service = LprRateService()
        return self._lpr_rate_service

    def calculate(self, params: InterestCalcParams) -> InterestCalcResult:
        """主入口：根据参数计算利息/违约金"""
        warnings: list[str] = []

        # 买卖合同不适用4倍LPR上限提示
        warnings.append(str(_("买卖合同不适用民间借贷4倍LPR利率上限")))

        # 违约金与利息不能同时全额主张提示
        if params.rate_type in (RateType.PENALTY_FIXED, RateType.PENALTY_DAILY):
            warnings.append(str(_("违约金与利息不能同时全额主张，建议择一主张或由法院酌定")))

        # 分批交货：每批独立计算
        if params.interest_start_type == InterestStartType.BATCH_DELIVERY:
            return self._calc_batch_delivery(params, warnings)

        # 确定计息起始日
        start = self._determine_start_date(params)
        if isinstance(start, list):
            # 不应到达此处（batch_delivery 已在上面处理）
            return self._calc_batch_delivery(params, warnings)

        end = params.end_date
        if start >= end:
            return InterestCalcResult(
                total_interest=_ZERO,
                segments=[],
                warnings=warnings,
            )

        total, segments = self._dispatch_calc(params, start, end)

        total = total.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        return InterestCalcResult(
            total_interest=total,
            segments=segments,
            warnings=warnings,
        )

    def _calc_batch_delivery(
        self, params: InterestCalcParams, warnings: list[str]
    ) -> InterestCalcResult:
        """分批交货：每批独立计算并累加"""
        if not params.batch_deliveries:
            return InterestCalcResult(
                total_interest=_ZERO,
                segments=[],
                warnings=warnings,
            )

        total = _ZERO
        all_segments: list[SegmentDetail] = []

        for batch in params.batch_deliveries:
            # 每批的起算日：约定付款日次日，或交货日次日
            if batch.payment_date is not None:
                batch_start = batch.payment_date + timedelta(days=1)
            else:
                batch_start = batch.delivery_date + timedelta(days=1)

            if batch_start >= params.end_date:
                continue

            batch_params = InterestCalcParams(
                principal=batch.amount,
                start_date=batch_start,
                end_date=params.end_date,
                rate_type=params.rate_type,
                agreed_rate=params.agreed_rate,
                penalty_amount=params.penalty_amount,
                penalty_daily_rate=params.penalty_daily_rate,
                lpr_markup=params.lpr_markup,
                interest_start_type=InterestStartType.AGREED_DATE,
                agreed_payment_date=None,
            )

            batch_total, batch_segments = self._dispatch_calc(
                batch_params, batch_start, params.end_date
            )
            total += batch_total
            all_segments.extend(batch_segments)

        total = total.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        return InterestCalcResult(
            total_interest=total,
            segments=all_segments,
            warnings=warnings,
        )

    def _dispatch_calc(
        self, params: InterestCalcParams, start: date, end: date
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """根据利率类型分发到对应计算方法"""
        if params.rate_type == RateType.LPR:
            return self._calc_lpr_interest(
                params.principal, start, end, params.lpr_markup
            )
        elif params.rate_type == RateType.AGREED_RATE:
            if params.agreed_rate is None:
                logger.info("合同约定利率未提供，使用LPR利率计算")
                return self._calc_lpr_interest(
                    params.principal, start, end, params.lpr_markup
                )
            return self._calc_agreed_rate(
                params.principal, start, end, params.agreed_rate
            )
        elif params.rate_type == RateType.PENALTY_FIXED:
            if params.penalty_amount is None:
                return _ZERO, []
            return self._calc_penalty_fixed(params.penalty_amount)
        elif params.rate_type == RateType.PENALTY_DAILY:
            if params.penalty_daily_rate is None:
                return _ZERO, []
            return self._calc_penalty_daily(
                params.principal, start, end, params.penalty_daily_rate
            )
        return _ZERO, []


    def _determine_start_date(
        self, params: InterestCalcParams
    ) -> date | list[tuple[date, Decimal]]:
        """根据 interest_start_type 确定计息起算日"""
        if params.interest_start_type == InterestStartType.AGREED_DATE:
            # 合同约定付款日的次日
            if params.agreed_payment_date is not None:
                return params.agreed_payment_date + timedelta(days=1)
            return params.start_date

        elif params.interest_start_type == InterestStartType.DEMAND_NOTICE:
            # 催告日期 + 合理期限天数 的次日
            if params.demand_date is not None:
                return params.demand_date + timedelta(
                    days=params.reasonable_period_days + 1
                )
            return params.start_date

        elif params.interest_start_type == InterestStartType.BATCH_DELIVERY:
            # 返回每批的 (起算日, 金额)
            if not params.batch_deliveries:
                return params.start_date
            result: list[tuple[date, Decimal]] = []
            for batch in params.batch_deliveries:
                if batch.payment_date is not None:
                    batch_start = batch.payment_date + timedelta(days=1)
                else:
                    batch_start = batch.delivery_date + timedelta(days=1)
                result.append((batch_start, batch.amount))
            return result

        return params.start_date

    def _calc_lpr_interest(
        self,
        principal: Decimal,
        start: date,
        end: date,
        markup: Decimal,
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """LPR分段计算：处理2019.8.20分水岭，逐段计算日利息并累加"""
        total = _ZERO
        segments: list[SegmentDetail] = []

        if start < LPR_WATERSHED:
            # 分水岭之前：使用旧基准利率
            pre_end = min(end, LPR_WATERSHED)
            days = (pre_end - start).days
            if days > 0:
                annual_rate = OLD_BENCHMARK_RATE_1Y + markup
                interest = (
                    principal * annual_rate / _HUNDRED / _DAYS_PER_YEAR * Decimal(days)
                )
                interest = interest.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
                total += interest
                segments.append(
                    SegmentDetail(
                        start_date=start,
                        end_date=pre_end,
                        days=days,
                        rate=annual_rate,
                        interest=interest,
                    )
                )
            # 分水岭之后的部分
            if end > LPR_WATERSHED:
                lpr_total, lpr_segments = self._calc_lpr_segments(
                    principal, LPR_WATERSHED, end, markup
                )
                total += lpr_total
                segments.extend(lpr_segments)
        else:
            # 全部在分水岭之后
            lpr_total, lpr_segments = self._calc_lpr_segments(
                principal, start, end, markup
            )
            total += lpr_total
            segments.extend(lpr_segments)

        return total, segments

    def _calc_lpr_segments(
        self,
        principal: Decimal,
        start: date,
        end: date,
        markup: Decimal,
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """使用 LprRateService 获取分段并逐段计算"""
        lpr_service = self._get_lpr_service()
        rate_segments = lpr_service.get_rate_segments(start, end)

        total = _ZERO
        segments: list[SegmentDetail] = []

        for seg in rate_segments:
            days = (seg.end - seg.start).days
            if days <= 0:
                continue
            annual_rate = seg.rate_1y + markup
            interest = (
                principal * annual_rate / _HUNDRED / _DAYS_PER_YEAR * Decimal(days)
            )
            interest = interest.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
            total += interest
            segments.append(
                SegmentDetail(
                    start_date=seg.start,
                    end_date=seg.end,
                    days=days,
                    rate=annual_rate,
                    interest=interest,
                )
            )

        return total, segments

    def _calc_agreed_rate(
        self,
        principal: Decimal,
        start: date,
        end: date,
        rate: Decimal,
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """合同约定利率计算"""
        days = (end - start).days
        if days <= 0:
            return _ZERO, []

        interest = principal * rate / _HUNDRED / _DAYS_PER_YEAR * Decimal(days)
        interest = interest.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        segment = SegmentDetail(
            start_date=start,
            end_date=end,
            days=days,
            rate=rate,
            interest=interest,
        )
        return interest, [segment]

    def _calc_penalty_fixed(
        self, amount: Decimal
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """固定违约金"""
        rounded = amount.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        return rounded, []

    def _calc_penalty_daily(
        self,
        principal: Decimal,
        start: date,
        end: date,
        daily_rate: Decimal,
    ) -> tuple[Decimal, list[SegmentDetail]]:
        """按日万分比违约金"""
        days = (end - start).days
        if days <= 0:
            return _ZERO, []

        interest = principal * daily_rate / _BASIS_POINTS * Decimal(days)
        interest = interest.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        # 将日万分比转换为年化利率用于展示
        annual_rate = (daily_rate / _BASIS_POINTS * _DAYS_PER_YEAR * _HUNDRED).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )

        segment = SegmentDetail(
            start_date=start,
            end_date=end,
            days=days,
            rate=annual_rate,
            interest=interest,
        )
        return interest, [segment]
