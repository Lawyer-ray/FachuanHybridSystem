"""
诉讼时效计算器

根据最后主张权利日期和中断事由计算诉讼时效状态
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum

logger = logging.getLogger(__name__)

LIMITATION_YEARS: int = 3
GUARANTEE_MONTHS: int = 6
EXPIRING_SOON_DAYS: int = 90


class InterruptionType(str, Enum):
    """时效中断事由类型"""

    COLLECTION = "collection"
    DEBTOR_PROMISE = "debtor_promise"
    LAWSUIT = "lawsuit"
    PAYMENT_ORDER = "payment_order"


@dataclass(frozen=True)
class InterruptionEvent:
    """时效中断事由"""

    event_type: InterruptionType
    event_date: date


@dataclass(frozen=True)
class LimitationCalcParams:
    """时效计算参数"""

    last_claim_date: date
    interruptions: list[InterruptionEvent]
    guarantee_debtor: bool = False
    principal_due_date: date | None = None


@dataclass(frozen=True)
class LimitationResult:
    """时效计算结果"""

    status: str
    expiry_date: date
    remaining_days: int
    base_date: date
    risk_warning: str
    guarantee_expiry_date: date | None = None


def _add_months(d: date, months: int) -> date:
    """日期加月数，处理月末溢出。"""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class LimitationCalculatorService:
    """诉讼时效计算服务"""

    def calculate(
        self,
        params: LimitationCalcParams,
        as_of: date | None = None,
    ) -> LimitationResult:
        """
        计算诉讼时效。

        1. 以 last_claim_date 为基准起算 3 年
        2. 如有中断事由，以最后一个中断日期重新起算
        3. 计算剩余天数和状态
        4. 如有保证人信息，计算保证期间
        """
        reference = as_of or date.today()
        base_date = params.last_claim_date

        if params.interruptions:
            sorted_events = sorted(params.interruptions, key=lambda e: e.event_date)
            base_date = sorted_events[-1].event_date

        expiry_date = date(
            base_date.year + LIMITATION_YEARS,
            base_date.month,
            base_date.day,
        )
        remaining_days = (expiry_date - reference).days

        if remaining_days <= 0:
            status = "expired"
            risk_warning = "诉讼时效已届满，建议立即采取法律行动或寻求时效中断事由"
        elif remaining_days <= EXPIRING_SOON_DAYS:
            status = "expiring_soon"
            risk_warning = f"距时效届满仅剩{remaining_days}天，建议尽快采取行动"
        else:
            status = "normal"
            risk_warning = ""

        guarantee_expiry: date | None = None
        if params.guarantee_debtor and params.principal_due_date:
            guarantee_expiry = _add_months(params.principal_due_date, GUARANTEE_MONTHS)

        return LimitationResult(
            status=status,
            expiry_date=expiry_date,
            remaining_days=remaining_days,
            base_date=base_date,
            risk_warning=risk_warning,
            guarantee_expiry_date=guarantee_expiry,
        )
