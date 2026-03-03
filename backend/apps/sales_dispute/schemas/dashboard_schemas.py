"""看板请求/响应 Schema"""

from __future__ import annotations

from datetime import date

from ninja import Schema

# ── 请求 Schema ──


class DateRangeQuery(Schema):
    """日期范围查询参数"""

    start_date: date | None = None
    end_date: date | None = None


class TrendQuery(DateRangeQuery):
    """趋势查询参数"""

    dimension: str = "month"  # month | quarter | year


class BreakdownQuery(DateRangeQuery):
    """分组查询参数"""

    group_by: str = "case_type"  # case_type | amount_range | lawyer


class LawyerPerformanceQuery(DateRangeQuery):
    """律师绩效查询参数"""

    sort_by: str = "total_recovery"  # total_recovery | recovery_rate | case_count


# ── 响应 Schema ──


class QueryPeriodSchema(Schema):
    """查询时间范围"""

    start_date: date
    end_date: date


class SummaryResponse(Schema):
    """核心指标响应"""

    total_recovery: str
    recovery_rate: str
    avg_recovery_cycle: int
    recovered_case_count: int
    unrecovered_case_count: int
    query_period: QueryPeriodSchema


class TrendItemResponse(Schema):
    """趋势项"""

    label: str
    amount: str
    count: int
    recovery_rate: str


class TrendResponse(Schema):
    """趋势响应"""

    items: list[TrendItemResponse]
    query_period: QueryPeriodSchema


class BreakdownItemResponse(Schema):
    """分组项"""

    group_label: str
    total_recovery: str
    case_count: int
    recovery_rate: str


class BreakdownResponse(Schema):
    """分组响应"""

    items: list[BreakdownItemResponse]
    query_period: QueryPeriodSchema


class FactorGroupResponse(Schema):
    """因素分组"""

    group_label: str
    case_count: int
    total_recovery: str
    recovery_rate: str


class FactorsResponse(Schema):
    """影响因素响应"""

    debt_age: list[FactorGroupResponse]
    contract_basis: list[FactorGroupResponse]
    preservation: list[FactorGroupResponse]
    amount_range: list[FactorGroupResponse]
    query_period: QueryPeriodSchema


class LawyerPerformanceItemResponse(Schema):
    """律师绩效项"""

    lawyer_id: int
    lawyer_name: str
    case_count: int
    total_recovery: str
    recovery_rate: str
    avg_recovery_cycle: int
    closed_rate: str


class LawyerPerformanceResponse(Schema):
    """律师绩效响应"""

    items: list[LawyerPerformanceItemResponse]
    query_period: QueryPeriodSchema


class CaseStatsResponse(Schema):
    """案件统计响应"""

    total_cases: int
    active_cases: int
    closed_cases: int
    stage_distribution: list[BreakdownItemResponse]
    amount_distribution: list[BreakdownItemResponse]
    stage_conversion_rates: list[FactorGroupResponse]
    query_period: QueryPeriodSchema
