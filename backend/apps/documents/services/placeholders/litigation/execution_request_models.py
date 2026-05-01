"""强制执行申请书 - 数据模型."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class FeeItem:
    key: str
    label: str
    amount: Decimal
    include: bool
    reason: str = ""
    sentence: str = ""


@dataclass
class ParsedAmounts:
    principal: Decimal | None = None
    principal_label: str = "借款本金"
    confirmed_interest: Decimal = Decimal("0")
    attorney_fee: Decimal = Decimal("0")
    guarantee_fee: Decimal = Decimal("0")
    litigation_fee: Decimal = Decimal("0")
    preservation_fee: Decimal = Decimal("0")
    announcement_fee: Decimal = Decimal("0")
    excluded_fees: list[FeeItem] = field(default_factory=list)


@dataclass
class ParsedInterestParams:
    start_date: date | None = None
    rate_type: str = "1y"
    multiplier: Decimal | None = None
    custom_rate_unit: str | None = None
    custom_rate_value: Decimal | None = None
    interest_cap: Decimal | None = None
    rate_description: str = ""
    overdue_item_label: str = "利息"
    base_mode: str = "fallback_target"
    base_amount: Decimal | None = None


@dataclass
class InterestSegment:
    base_amount: Decimal
    start_date: date
    end_date: date | None = None


@dataclass
class OverdueInterestRule:
    params: ParsedInterestParams
    segments: list[InterestSegment] = field(default_factory=list)
    source_text: str = ""


@dataclass
class ExecutionComputation:
    preview_text: str
    warnings: list[str]
    structured_params: dict[str, Any]
