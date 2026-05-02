"""回款统计看板 — 数据模型与工具函数"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils.translation import gettext as _

_ZERO = Decimal("0.00")


# ── 输出 dataclass ──


@dataclass(frozen=True)
class SummaryOutput:
    """核心指标输出"""

    total_recovery: Decimal
    recovery_rate: Decimal
    avg_recovery_cycle: int
    recovered_case_count: int
    unrecovered_case_count: int
    query_start: date
    query_end: date


@dataclass(frozen=True)
class TrendItem:
    """趋势分组项"""

    label: str
    amount: Decimal
    count: int
    recovery_rate: Decimal


@dataclass(frozen=True)
class BreakdownItem:
    """分组统计项"""

    group_label: str
    total_recovery: Decimal
    case_count: int
    recovery_rate: Decimal


@dataclass(frozen=True)
class FactorItem:
    """影响因素分析项"""

    group_label: str
    case_count: int
    total_recovery: Decimal
    recovery_rate: Decimal


@dataclass(frozen=True)
class LawyerPerformanceItem:
    """律师绩效项"""

    lawyer_id: int
    lawyer_name: str
    case_count: int
    total_recovery: Decimal
    recovery_rate: Decimal
    avg_recovery_cycle: int
    closed_rate: Decimal


@dataclass(frozen=True)
class CaseStatsOutput:
    """案件统计输出"""

    total_cases: int
    active_cases: int
    closed_cases: int
    stage_distribution: list[BreakdownItem]
    amount_distribution: list[BreakdownItem]
    stage_conversion_rates: list[FactorItem]
    query_start: date
    query_end: date


# ── 常量 ──

AMOUNT_RANGES: list[tuple[str, Decimal | None, Decimal | None]] = [
    (_("10万以下"), None, Decimal("100000")),
    (_("10万-50万"), Decimal("100000"), Decimal("500000")),
    (_("50万-100万"), Decimal("500000"), Decimal("1000000")),
    (_("100万以上"), Decimal("1000000"), None),
]

DEBT_AGE_RANGES: list[tuple[str, int | None, int | None]] = [
    (_("1年内"), None, 365),
    (_("1-2年"), 365, 730),
    (_("2年以上"), 730, None),
]


# ── 工具函数 ──


def _safe_rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    """除零保护的百分比计算"""
    if denominator == 0:
        return _ZERO
    return (numerator / denominator * 100).quantize(Decimal("0.01"))


def _amount_range_q(
    field: str,
    low: Decimal | None,
    high: Decimal | None,
) -> Q:
    """构建金额区间 Q 对象"""
    q = Q()
    if low is not None:
        q &= Q(**{f"{field}__gte": low})
    if high is not None:
        q &= Q(**{f"{field}__lt": high})
    return q


def _get_case_model() -> type[Any]:
    return django_apps.get_model("cases", "Case")


def _get_case_assignment_model() -> type[Any]:
    return django_apps.get_model("cases", "CaseAssignment")


def _lawyer_display_name(lawyer: object | None) -> str:
    if lawyer is None:
        return _("未知律师")
    return getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or _("未知律师")
