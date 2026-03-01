"""
还款冲抵引擎

按《民法典》560条规则处理还款冲抵：
- 同一笔债务内：费用 → 利息 → 本金
- 多笔债务（无约定时）：先到期 → 缺乏担保 → 负担较重
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.sales_dispute.models.payment_record import PaymentRecord
    from apps.sales_dispute.services.interest_calculator_service import (
        InterestCalcParams,
        InterestCalculatorService,
    )

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_TWO_PLACES = Decimal("0.01")


@dataclass
class DebtItem:
    """单笔债务"""

    principal: Decimal
    accrued_fee: Decimal
    accrued_interest: Decimal
    due_date: date
    has_guarantee: bool
    debt_id: str


@dataclass
class OffsetDetail:
    """单笔债务的冲抵明细"""

    debt_id: str
    offset_fee: Decimal
    offset_interest: Decimal
    offset_principal: Decimal
    remaining_principal: Decimal


@dataclass
class OffsetResult:
    """单笔还款的冲抵结果"""

    payment_date: date
    payment_amount: Decimal
    details: list[OffsetDetail]
    remaining_debts: list[DebtItem]


@dataclass
class PaymentInput:
    """还款输入"""

    payment_date: date
    payment_amount: Decimal


class RepaymentOffsetService:
    """还款冲抵引擎"""

    def __init__(
        self, interest_calculator: InterestCalculatorService | None = None
    ) -> None:
        self._interest_calculator = interest_calculator

    def _get_interest_calculator(self) -> InterestCalculatorService:
        """延迟获取 InterestCalculatorService 实例"""
        if self._interest_calculator is None:
            from apps.sales_dispute.services.interest_calculator_service import (
                InterestCalculatorService,
            )

            self._interest_calculator = InterestCalculatorService()
        return self._interest_calculator

    def offset_single_debt(
        self,
        payment_amount: Decimal,
        fee: Decimal,
        interest: Decimal,
        principal: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        单笔债务冲抵：费用→利息→本金

        返回 (offset_fee, offset_interest, offset_principal, remaining_principal)
        """
        remaining = payment_amount

        offset_fee = min(remaining, fee)
        remaining -= offset_fee

        offset_interest = min(remaining, interest)
        remaining -= offset_interest

        offset_principal = min(remaining, principal)

        remaining_principal = principal - offset_principal

        return (
            offset_fee.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
            offset_interest.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
            offset_principal.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
            remaining_principal.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
        )

    def offset_multiple_debts(
        self,
        payment_amount: Decimal,
        debts: list[DebtItem],
        custom_order: list[str] | None = None,
    ) -> OffsetResult:
        """
        多笔债务冲抵：按约定顺序或法定优先级排序后逐笔冲抵

        法定优先级（《民法典》560条，无约定时）：
        1. 先到期的债务 (due_date ASC)
        2. 缺乏担保的债务 (has_guarantee ASC, False 排前)
        3. 负担较重的债务 (accrued_interest DESC)
        """
        if custom_order is not None:
            order_map = {did: idx for idx, did in enumerate(custom_order)}
            sorted_debts = sorted(
                debts,
                key=lambda d: order_map.get(d.debt_id, len(custom_order)),
            )
        else:
            sorted_debts = sorted(
                debts,
                key=lambda d: (
                    d.due_date,
                    d.has_guarantee,
                    -d.accrued_interest,
                ),
            )

        remaining = payment_amount
        details: list[OffsetDetail] = []
        updated_debts: list[DebtItem] = []

        for debt in sorted_debts:
            if remaining <= _ZERO:
                # 无剩余还款金额，债务不变
                updated_debts.append(debt)
                details.append(
                    OffsetDetail(
                        debt_id=debt.debt_id,
                        offset_fee=_ZERO,
                        offset_interest=_ZERO,
                        offset_principal=_ZERO,
                        remaining_principal=debt.principal,
                    )
                )
                continue

            offset_fee, offset_interest, offset_principal, rem_principal = (
                self.offset_single_debt(
                    remaining,
                    debt.accrued_fee,
                    debt.accrued_interest,
                    debt.principal,
                )
            )

            used = offset_fee + offset_interest + offset_principal
            remaining -= used

            details.append(
                OffsetDetail(
                    debt_id=debt.debt_id,
                    offset_fee=offset_fee,
                    offset_interest=offset_interest,
                    offset_principal=offset_principal,
                    remaining_principal=rem_principal,
                )
            )

            updated_debts.append(
                DebtItem(
                    principal=rem_principal,
                    accrued_fee=debt.accrued_fee - offset_fee,
                    accrued_interest=debt.accrued_interest - offset_interest,
                    due_date=debt.due_date,
                    has_guarantee=debt.has_guarantee,
                    debt_id=debt.debt_id,
                )
            )

        return OffsetResult(
            payment_date=date.today(),
            payment_amount=payment_amount,
            details=details,
            remaining_debts=updated_debts,
        )

    def process_payment_series(
        self,
        case_id: int,
        principal: Decimal,
        payments: list[PaymentInput],
        interest_params: InterestCalcParams,
    ) -> list[PaymentRecord]:
        """
        处理一系列还款：每笔还款后重算剩余本金的后续利息，生成 PaymentRecord 列表（不保存）
        """
        from apps.sales_dispute.models import PaymentRecord

        calculator = self._get_interest_calculator()
        sorted_payments = sorted(payments, key=lambda p: p.payment_date)

        current_principal = principal
        last_date = interest_params.start_date
        records: list[PaymentRecord] = []

        for payment in sorted_payments:
            if current_principal <= _ZERO:
                break

            # 计算从上次还款日到本次还款日的利息
            accrued_interest = _ZERO
            if payment.payment_date > last_date:
                from apps.sales_dispute.services.interest_calculator_service import (
                    InterestCalcParams as _ICP,
                )

                calc_params = _ICP(
                    principal=current_principal,
                    start_date=last_date,
                    end_date=payment.payment_date,
                    rate_type=interest_params.rate_type,
                    agreed_rate=interest_params.agreed_rate,
                    penalty_daily_rate=interest_params.penalty_daily_rate,
                    lpr_markup=interest_params.lpr_markup,
                )
                result = calculator.calculate(calc_params)
                accrued_interest = result.total_interest

            # 冲抵：费用=0，利息=计算所得，本金=当前剩余
            offset_fee, offset_interest, offset_principal, remaining = (
                self.offset_single_debt(
                    payment.payment_amount,
                    _ZERO,
                    accrued_interest,
                    current_principal,
                )
            )

            record = PaymentRecord(
                case_id=case_id,
                payment_date=payment.payment_date,
                payment_amount=payment.payment_amount,
                offset_fee=offset_fee,
                offset_interest=offset_interest,
                offset_principal=offset_principal,
                remaining_principal=remaining,
            )
            records.append(record)

            current_principal = remaining
            last_date = payment.payment_date

            logger.info(
                "还款冲抵: date=%s amount=%s fee=%s interest=%s principal=%s remaining=%s",
                payment.payment_date,
                payment.payment_amount,
                offset_fee,
                offset_interest,
                offset_principal,
                remaining,
            )

        return records
