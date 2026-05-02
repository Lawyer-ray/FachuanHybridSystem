"""买卖纠纷计算 API — 看板端点。"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext as _
from ninja import Query, Router
from ninja.errors import HttpError

from apps.sales_dispute.schemas import (
    BreakdownItemResponse,
    BreakdownQuery,
    BreakdownResponse,
    CaseStatsResponse,
    DateRangeQuery,
    FactorGroupResponse,
    FactorsResponse,
    LawyerPerformanceItemResponse,
    LawyerPerformanceQuery,
    LawyerPerformanceResponse,
    QueryPeriodSchema,
    SummaryResponse,
    TrendItemResponse,
    TrendQuery,
    TrendResponse,
)

from .sales_dispute_api_factories import _get_dashboard_service, _resolve_date_range

router = Router()


@router.get("/dashboard/summary", response=SummaryResponse)
def get_dashboard_summary(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """核心指标统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    out = svc.get_summary(s, e)
    return SummaryResponse(
        total_recovery=str(out.total_recovery),
        recovery_rate=str(out.recovery_rate),
        avg_recovery_cycle=out.avg_recovery_cycle,
        recovered_case_count=out.recovered_case_count,
        unrecovered_case_count=out.unrecovered_case_count,
        query_period=QueryPeriodSchema(start_date=out.query_start, end_date=out.query_end),
    )


@router.get("/dashboard/trend", response=TrendResponse)
def get_dashboard_trend(
    request: HttpRequest,
    query: Query[TrendQuery],
) -> Any:
    """回款趋势"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_dims = {"month", "quarter", "year"}
    if query.dimension not in valid_dims:
        raise HttpError(422, _("时间维度参数无效，可选值：month, quarter, year"))
    svc = _get_dashboard_service()
    items = svc.get_trend(s, e, query.dimension)
    return TrendResponse(
        items=[
            TrendItemResponse(
                label=it.label,
                amount=str(it.amount),
                count=it.count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/breakdown", response=BreakdownResponse)
def get_dashboard_breakdown(
    request: HttpRequest,
    query: Query[BreakdownQuery],
) -> Any:
    """多维度分组统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_groups = {"case_type", "amount_range", "lawyer"}
    if query.group_by not in valid_groups:
        raise HttpError(422, _("分组参数无效，可选值：case_type, amount_range, lawyer"))
    svc = _get_dashboard_service()
    items = svc.get_breakdown(s, e, query.group_by)
    return BreakdownResponse(
        items=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/factors", response=FactorsResponse)
def get_dashboard_factors(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """回款影响因素分析"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    result = svc.get_factors(s, e)

    def _to_factor_resp(items: list[Any]) -> list[FactorGroupResponse]:
        return [
            FactorGroupResponse(
                group_label=it.group_label,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
            )
            for it in items
        ]

    return FactorsResponse(
        debt_age=_to_factor_resp(result["debt_age"]),
        contract_basis=_to_factor_resp(result["contract_basis"]),
        preservation=_to_factor_resp(result["preservation"]),
        amount_range=_to_factor_resp(result["amount_range"]),
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/lawyer-performance", response=LawyerPerformanceResponse)
def get_dashboard_lawyer_performance(
    request: HttpRequest,
    query: Query[LawyerPerformanceQuery],
) -> Any:
    """律师绩效分析"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    valid_sorts = {"total_recovery", "recovery_rate", "case_count"}
    if query.sort_by not in valid_sorts:
        raise HttpError(422, _("排序参数无效，可选值：total_recovery, recovery_rate, case_count"))
    svc = _get_dashboard_service()
    items = svc.get_lawyer_performance(s, e, query.sort_by)
    return LawyerPerformanceResponse(
        items=[
            LawyerPerformanceItemResponse(
                lawyer_id=it.lawyer_id,
                lawyer_name=it.lawyer_name,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
                avg_recovery_cycle=it.avg_recovery_cycle,
                closed_rate=str(it.closed_rate),
            )
            for it in items
        ],
        query_period=QueryPeriodSchema(start_date=s, end_date=e),
    )


@router.get("/dashboard/case-stats", response=CaseStatsResponse)
def get_dashboard_case_stats(
    request: HttpRequest,
    query: Query[DateRangeQuery],
) -> Any:
    """案件数据统计"""
    s, e = _resolve_date_range(query.start_date, query.end_date)
    if query.start_date and query.end_date and s > e:
        raise HttpError(422, _("起始日期不能晚于结束日期"))
    svc = _get_dashboard_service()
    out = svc.get_case_stats(s, e)
    return CaseStatsResponse(
        total_cases=out.total_cases,
        active_cases=out.active_cases,
        closed_cases=out.closed_cases,
        stage_distribution=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.stage_distribution
        ],
        amount_distribution=[
            BreakdownItemResponse(
                group_label=it.group_label,
                total_recovery=str(it.total_recovery),
                case_count=it.case_count,
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.amount_distribution
        ],
        stage_conversion_rates=[
            FactorGroupResponse(
                group_label=it.group_label,
                case_count=it.case_count,
                total_recovery=str(it.total_recovery),
                recovery_rate=str(it.recovery_rate),
            )
            for it in out.stage_conversion_rates
        ],
        query_period=QueryPeriodSchema(start_date=out.query_start, end_date=out.query_end),
    )
