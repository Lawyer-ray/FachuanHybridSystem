"""房贷逾期计算：利率解析（合同利率 / 罚息利率 / 逾期加码 / 封顶）.

单一职责：给定日期返回适用的合同年利率与罚息年利率。纯计算，无数据库副作用。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.mortgage_models import PENALTY_MODE_SPECIFIED, RATE_MODE_FIXED, RATE_MODE_LPR

if TYPE_CHECKING:
    from apps.finance.services.lpr.rate_service import LPRRateService


def safe_date(year: int, month: int, day: int) -> date:
    """构造日期，月末越界时钳制（2 月取 28/29，其余取 30）."""
    day = min(day, 28 if month == 2 else 30)
    return date(year, month, day)


def last_repricing_date(start_date: date, on: date, repricing_day: str) -> date:
    """返回 on 之前（含）最近的重定价日；无则返回放款日（初始定价）."""
    if repricing_day == "anniversary":
        month, day = start_date.month, start_date.day
    else:
        month_s, day_s = repricing_day.split("-")
        month, day = int(month_s), int(day_s)

    for year in range(on.year, start_date.year - 1, -1):
        candidate = safe_date(year, month, day)
        if candidate <= on and candidate >= start_date:
            return candidate
        if candidate < start_date and year == start_date.year:
            break
    return start_date


class RateResolver:
    """合同利率与罚息利率的统一解析入口.

    Args:
        rate_mode: fixed=固定利率，lpr=LPR+基点浮动
        fixed_rate: 固定年利率（%），固定模式必填
        rate_service: LPR 利率查询服务（lpr 模式）
        lpr_type: LPR 期限品种，1y 或 5y
        basis_points: LPR 基础上加的基点（bp，100bp=1%）
        repricing_day: 重定价日，"01-01"、"anniversary"、"MM-DD"
        start_date: 放款日
        rate_events: 分段利率事件列表（自事件日起覆盖基座利率）
        penalty_mode: multiplier=执行利率×倍数，specified=直接指定罚息年利率
        penalty_multiplier: 罚息倍数（multiplier 模式）
        penalty_rate: 罚息年利率（%），specified 模式必填
        cap_penalty_annual: 罚息/复利年利率封顶（%），None 不封顶
    """

    def __init__(
        self,
        *,
        rate_mode: str,
        fixed_rate: Decimal | None,
        rate_service: LPRRateService | None,
        lpr_type: str,
        basis_points: Decimal,
        repricing_day: str,
        start_date: date,
        rate_events: list[dict] | None,
        penalty_mode: str,
        penalty_multiplier: Decimal,
        penalty_rate: Decimal | None,
        cap_penalty_annual: Decimal | None,
        step_up_rate: Decimal | None,
        step_up_trigger_days: int,
    ) -> None:
        self.rate_mode = rate_mode
        self.fixed_rate = fixed_rate
        self.rate_service = rate_service
        self.lpr_type = lpr_type
        self.basis_points = basis_points
        self.repricing_day = repricing_day
        self.start_date = start_date
        self.rate_events = self._validate_events(rate_events)
        self.penalty_mode = penalty_mode
        self.penalty_multiplier = penalty_multiplier
        self.penalty_rate = penalty_rate
        self.cap_penalty_annual = cap_penalty_annual
        self.step_up_rate = step_up_rate
        self.step_up_trigger_days = step_up_trigger_days

    @staticmethod
    def _validate_events(rate_events: list[dict] | None) -> list[dict]:
        """校验分段利率事件合法性，非法项抛出避免静默错误."""
        for ev in rate_events or []:
            if not ev.get("date") or ev.get("annual_rate") is None:
                raise ValidationException(
                    message="分段利率事件需同时提供 date 与 annual_rate",
                    code="INVALID_RATE_EVENT",
                )
        return sorted((rate_events or []), key=lambda e: date.fromisoformat(str(e.get("date"))))

    def _base_contract_rate(self, on: date) -> Decimal:
        """无分段事件时的基座合同年利率（固定或 LPR+基点）."""
        if self.rate_mode == RATE_MODE_FIXED:
            assert self.fixed_rate is not None  # validation 已保证
            return self.fixed_rate

        cache: dict[date, Decimal] = {}

        def resolve(on_: date) -> Decimal:
            rdate = last_repricing_date(self.start_date, on_, self.repricing_day)
            if rdate not in cache:
                assert self.rate_service is not None
                rate = self.rate_service.get_rate_at(rdate)
                base = rate.rate_5y if self.lpr_type == "5y" else rate.rate_1y
                cache[rdate] = base + self.basis_points / Decimal("100")
            return cache[rdate]

        return resolve(on)

    def contract_annual(self, on: date) -> Decimal:
        """给定日期返回适用的合同年利率（%），分段利率事件具有最高优先级."""
        applied: Decimal | None = None
        for ev in self.rate_events:
            ev_date = ev.get("date")
            if isinstance(ev_date, str):
                ev_date = date.fromisoformat(ev_date)
            if ev_date is None:
                continue
            if on >= ev_date:
                applied = Decimal(str(ev.get("annual_rate")))
            else:
                break
        if applied is not None:
            return applied
        return self._base_contract_rate(on)

    def penalty_annual(self, on: date) -> Decimal:
        """给定日期返回适用的罚息年利率（%），并应用年利率封顶."""
        if self.penalty_mode == PENALTY_MODE_SPECIFIED:
            assert self.penalty_rate is not None  # validation 已保证
            r = self.penalty_rate
        else:
            r = self.contract_annual(on) * self.penalty_multiplier
        if self.cap_penalty_annual is not None and r > self.cap_penalty_annual:
            r = self.cap_penalty_annual
        return r

    def eff_penalty_annual(self, on: date, first_penalty_start: date | None) -> Decimal:
        """罚息年利率（%），按 on 判断是否已触发逾期自动加码，并应用年利率封顶."""
        r = self.penalty_annual(on)
        if self.step_up_rate is not None and first_penalty_start is not None:
            if on >= first_penalty_start + timedelta(days=self.step_up_trigger_days):
                r = r * (Decimal("1") + self.step_up_rate / Decimal("100"))
        if self.cap_penalty_annual is not None and r > self.cap_penalty_annual:
            r = self.cap_penalty_annual
        return r
