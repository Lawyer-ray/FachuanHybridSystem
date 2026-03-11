"""LPR利息计算器.

提供基于LPR的利息计算功能，支持：
- 变动本金分段计算（如租金场景）
- 多种计息天数基准（360/365/实际天数）
- LPR利率变动自动分段
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.finance.services.lpr.rate_service import PrincipalPeriod

if TYPE_CHECKING:
    from apps.finance.services.lpr.rate_service import LPRRateService, RateSegment

logger = logging.getLogger(__name__)


@dataclass
class CalculationPeriod:
    """最小计算单元.

    在最小时间段内，本金和利率都是固定的。

    Attributes:
        start_date: 开始日期
        end_date: 结束日期
        principal: 本金
        rate: 年利率(%)
        days: 计息天数
        year_days: 年基准天数(360/365/实际天数)
        interest: 利息
    """

    start_date: date
    end_date: date
    principal: Decimal
    rate: Decimal
    days: int = 0
    year_days: int = 365
    interest: Decimal = field(default_factory=lambda: Decimal("0"))

    def calculate(self) -> Decimal:
        """计算该期间的利息.

        公式：利息 = 本金 × 年利率 × 计息天数 / 年基准天数

        Returns:
            利息金额
        """
        if self.days <= 0:
            return Decimal("0")

        rate_decimal = self.rate / Decimal("100")
        self.interest = self.principal * rate_decimal * Decimal(self.days) / Decimal(self.year_days)
        return self.interest.quantize(Decimal("0.01"))


@dataclass
class InterestCalculationResult:
    """利息计算结果.

    Attributes:
        total_interest: 总利息
        total_principal: 总本金（加权平均）
        total_days: 总计息天数
        periods: 各分段计算明细
        start_date: 计算开始日期
        end_date: 计算结束日期
    """

    total_interest: Decimal
    total_principal: Decimal
    total_days: int
    periods: list[CalculationPeriod]
    start_date: date
    end_date: date

    def to_dict(self) -> dict:
        """转换为字典格式."""
        return {
            "total_interest": str(self.total_interest),
            "total_principal": str(self.total_principal),
            "total_days": self.total_days,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "periods": [
                {
                    "start_date": p.start_date.isoformat(),
                    "end_date": p.end_date.isoformat(),
                    "principal": str(p.principal),
                    "rate": str(p.rate),
                    "days": p.days,
                    "year_days": p.year_days,
                    "interest": str(p.interest),
                }
                for p in self.periods
            ],
        }


class InterestCalculator:
    """LPR利息计算器.

    支持固定本金和变动本金两种计算模式。
    """

    def __init__(self, rate_service: LPRRateService | None = None) -> None:
        """Initialize calculator.

        Args:
            rate_service: LPR利率查询服务，如不提供则自动创建
        """
        if rate_service is None:
            from apps.finance.services.lpr.rate_service import LPRRateService
            self.rate_service = LPRRateService()
        else:
            self.rate_service = rate_service

    def calculate(
        self,
        start_date: date,
        end_date: date,
        principal: Decimal,
        rate_type: str = "1y",
        year_days: int = 365,
        multiplier: Decimal = Decimal("1"),
        date_inclusion: str = "both",
    ) -> InterestCalculationResult:
        """计算固定本金的利息.

        Args:
            start_date: 开始日期
            end_date: 结束日期
            principal: 本金
            rate_type: 利率类型，"1y" 或 "5y"
            year_days: 年基准天数，360/365/0(实际天数)
            multiplier: 利率倍数（如逾期按LPR的1.5倍计算）
            date_inclusion: 日期计算方式，both/start_only/end_only/neither

        Returns:
            计算结果
        """
        if start_date > end_date:
            raise ValidationException(
                message=_("开始日期必须早于或等于结束日期"),
                code="INVALID_DATE_RANGE"
            )

        if principal <= 0:
            raise ValidationException(
                message=_("本金必须大于0"),
                code="INVALID_PRINCIPAL"
            )

        # 根据日期包含模式调整计算用日期
        calc_start, calc_end = self._apply_date_inclusion(start_date, end_date, date_inclusion)

        # 获取利率分段
        rate_segments = self.rate_service.get_rate_segments(calc_start, calc_end)

        # 创建本金时间段（固定本金只有一个时间段）
        principal_periods = [PrincipalPeriod(calc_start, calc_end, principal)]

        # 交叉分段计算
        return self._calculate_cross_segments(
            principal_periods, rate_segments, rate_type, year_days, multiplier
        )

    def _apply_date_inclusion(
        self, start_date: date, end_date: date, date_inclusion: str
    ) -> tuple[date, date]:
        """根据日期包含模式调整计算用日期.

        Args:
            start_date: 原始开始日期
            end_date: 原始结束日期
            date_inclusion: 日期计算方式

        Returns:
            调整后的 (calc_start, calc_end)
        """
        from datetime import timedelta

        calc_start = start_date
        calc_end = end_date

        if date_inclusion == "neither":
            # 起止日期均不计算在内：开始日期+1，结束日期-1
            calc_start = start_date + timedelta(days=1)
            calc_end = end_date - timedelta(days=1)
        elif date_inclusion == "start_only":
            # 仅起始日期计算在内：结束日期-1
            calc_end = end_date - timedelta(days=1)
        elif date_inclusion == "end_only":
            # 仅截止日期计算在内：开始日期+1
            calc_start = start_date + timedelta(days=1)
        # else: both - 起止日期均计算在内，无需调整

        # 确保开始日期不晚于结束日期
        if calc_start > calc_end:
            calc_end = calc_start

        return calc_start, calc_end

    def calculate_with_principal_changes(
        self,
        principal_periods: list[PrincipalPeriod],
        rate_type: str = "1y",
        year_days: int = 365,
        multiplier: Decimal = Decimal("1"),
        date_inclusion: str = "both",
    ) -> InterestCalculationResult:
        """计算变动本金的利息.

        适用于租金等本金随时间变化的场景。

        Args:
            principal_periods: 本金变动时间段列表
            rate_type: 利率类型，"1y" 或 "5y"
            year_days: 年基准天数，360/365/0(实际天数)
            multiplier: 利率倍数
            date_inclusion: 日期计算方式

        Returns:
            计算结果
        """
        if not principal_periods:
            raise ValidationException(
                message=_("本金时间段不能为空"),
                code="EMPTY_PRINCIPAL_PERIODS"
            )

        # 排序并验证
        principal_periods = sorted(principal_periods, key=lambda x: x.start_date)
        self._validate_principal_periods(principal_periods)

        # 根据日期包含模式调整每个本金时间段
        adjusted_periods = []
        for pp in principal_periods:
            calc_start, calc_end = self._apply_date_inclusion(
                pp.start_date, pp.end_date, date_inclusion
            )
            adjusted_periods.append(PrincipalPeriod(calc_start, calc_end, pp.principal))

        start_date = adjusted_periods[0].start_date
        end_date = adjusted_periods[-1].end_date

        # 获取利率分段
        rate_segments = self.rate_service.get_rate_segments(start_date, end_date)

        # 交叉分段计算
        return self._calculate_cross_segments(
            adjusted_periods, rate_segments, rate_type, year_days, multiplier
        )

    def _calculate_cross_segments(
        self,
        principal_periods: list[PrincipalPeriod],
        rate_segments: list[RateSegment],
        rate_type: str,
        year_days: int,
        multiplier: Decimal,
    ) -> InterestCalculationResult:
        """交叉分段计算.

        将本金变动时间段和利率变动时间段交叉，得到最小计算单元。

        Args:
            principal_periods: 本金时间段列表
            rate_segments: 利率时间段列表
            rate_type: 利率类型
            year_days: 年基准天数
            multiplier: 利率倍数

        Returns:
            计算结果
        """
        periods: list[CalculationPeriod] = []
        total_interest = Decimal("0")
        total_days = 0

        for pp in principal_periods:
            for rs in rate_segments:
                # 计算两个时间段的交集
                seg_start = max(pp.start_date, rs.start)
                seg_end = min(pp.end_date, rs.end)

                if seg_start >= seg_end:
                    continue

                # 确定利率
                rate = rs.rate_1y if rate_type == "1y" else rs.rate_5y
                rate = rate * Decimal(str(multiplier))

                # 确定年基准天数
                actual_year_days = self._get_year_days(seg_start, seg_end, year_days)

                # 计算天数（闭区间，包含起止日期）
                days = (seg_end - seg_start).days + 1

                # 创建计算单元
                period = CalculationPeriod(
                    start_date=seg_start,
                    end_date=seg_end,
                    principal=pp.principal,
                    rate=rate,
                    days=days,
                    year_days=actual_year_days,
                )

                # 计算利息
                period.calculate()
                periods.append(period)

                total_interest += period.interest
                total_days += days

        if not periods:
            raise ValidationException(
                message=_("无法计算利息，请检查日期范围和利率数据"),
                code="CALCULATION_FAILED"
            )

        # 计算加权平均本金
        total_principal_weighted = sum(
            Decimal(str(p.principal)) * p.days for p in periods
        )
        total_principal = (total_principal_weighted / Decimal(str(total_days))).quantize(Decimal("0.01")) if total_days > 0 else Decimal("0")

        return InterestCalculationResult(
            total_interest=total_interest.quantize(Decimal("0.01")),
            total_principal=total_principal.quantize(Decimal("0.01")),
            total_days=total_days,
            periods=periods,
            start_date=periods[0].start_date,
            end_date=periods[-1].end_date,
        )

    def _validate_principal_periods(self, periods: list[PrincipalPeriod]) -> None:
        """验证本金时间段.

        Args:
            periods: 本金时间段列表

        Raises:
            ValidationException: 验证失败
        """
        for i in range(len(periods)):
            period = periods[i]

            # 验证本金大于0
            if period.principal <= 0:
                raise ValidationException(
                    message=_("第%(index)s段本金必须大于0") % {"index": i + 1},
                    code="INVALID_PRINCIPAL"
                )

            # 验证开始日期不晚于结束日期
            if period.start_date > period.end_date:
                raise ValidationException(
                    message=_("第%(index)s段开始日期不能晚于结束日期") % {"index": i + 1},
                    code="INVALID_DATE_RANGE"
                )

        # 注意：时间段之间允许有空隙，不强制连续
        # 例如：第一段10/01-10/31，第二段11/01-11/30 是合法的（即使中间有空隙）

    def _get_year_days(self, start_date: date, end_date: date, year_days: int) -> int:
        """确定年基准天数.

        Args:
            start_date: 开始日期
            end_date: 结束日期
            year_days: 用户指定的年基准天数，0表示使用实际天数

        Returns:
            年基准天数
        """
        if year_days == 0:
            # 使用实际天数（判断是否为闰年）
            year = start_date.year
            if calendar.isleap(year):
                return 366
            return 365
        return year_days

    @staticmethod
    def create_principal_periods(
        changes: list[dict],
        default_principal: Decimal = Decimal("0"),
    ) -> list[PrincipalPeriod]:
        """从配置创建本金时间段.

        Args:
            changes: 本金变动列表，每项包含 start_date, end_date, principal
            default_principal: 默认本金

        Returns:
            本金时间段列表
        """
        periods = []
        for change in changes:
            period = PrincipalPeriod(
                start_date=change["start_date"],
                end_date=change["end_date"],
                principal=Decimal(str(change.get("principal", default_principal))),
            )
            periods.append(period)

        return sorted(periods, key=lambda x: x.start_date)
