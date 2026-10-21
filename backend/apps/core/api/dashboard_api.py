"""仪表盘聚合统计 API"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["仪表盘"])


# ─── Schemas ────────────────────────────────────────────────────────────────────


class TrendItem(Schema):
    month: str
    count: int = 0
    amount: str = "0"


class CaseTypeDistItem(Schema):
    type: str
    label: str
    count: int


class UpcomingReminderItem(Schema):
    id: int
    title: str
    due_at: str
    type_label: str
    is_overdue: bool


class DashboardStatsOut(Schema):
    client_count: int = 0
    contract_count: int = 0
    case_count: int = 0
    monthly_fee: str = "0"
    case_trend: list[TrendItem] = []
    contract_trend: list[TrendItem] = []
    fee_trend: list[TrendItem] = []
    case_type_distribution: list[CaseTypeDistItem] = []
    case_status_distribution: dict[str, int] = {}
    upcoming_reminders: list[UpcomingReminderItem] = []
    overdue_count: int = 0
    today_count: int = 0


# ─── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/stats", response=DashboardStatsOut)
async def get_dashboard_stats(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """返回仪表盘聚合统计数据。

    9 条独立 DB 查询通过 asyncio.gather 并发执行，
    延迟从 9 次串行降低到最慢那一次。
    用 Semaphore 限制并发为 4，避免线程池耗尽和 DB 连接暴涨。
    """
    import asyncio

    from apps.core.security import get_request_access_context
    from apps.core.services.dashboard_service import (
        DashboardService,
        _case_status_distribution,
        _case_trend,
        _case_type_stats,
        _client_count,
        _contract_count,
        _contract_trend,
        _fee_stats,
        _reminder_counts,
        _upcoming_reminders,
    )

    service = DashboardService()

    # 安全审计（2026-10-19）：提醒列表接入读范围过滤（scope_reminders_for_context），
    # 非管理员不再看到他人案件的提醒 content 原文；ctx 按请求构造后传入 service。
    # 计数与财务聚合（monthly_fee、全所计数、trend 等）暂保持全所口径，待产品拍板。
    ctx = await sync_to_async(get_request_access_context)(request)

    # thread_sensitive=False 让每个调用在独立线程中执行，实现真正并行
    stf = sync_to_async(thread_sensitive=False)

    # M3 修复：限制并发线程数为 4，避免 9 线程同时抢占连接池
    sem = asyncio.Semaphore(4)

    async def _guarded(coro: Any) -> Any:
        async with sem:
            return await coro

    (
        case_type_dist_and_count,
        case_trend,
        case_status_dist,
        fee_stats,
        reminder_counts,
        upcoming_reminders,
        client_count,
        contract_count,
        contract_trend,
    ) = await asyncio.gather(
        _guarded(stf(_case_type_stats)()),
        _guarded(stf(_case_trend)(timezone.localdate() - timedelta(days=365))),
        _guarded(stf(_case_status_distribution)()),
        _guarded(
            stf(_fee_stats)(
                timezone.localdate().replace(day=1), timezone.localdate(), timezone.localdate() - timedelta(days=365)
            )
        ),
        _guarded(stf(_reminder_counts)(timezone.now())),
        # 安全审计（2026-10-19）：提醒列表必须带 ctx 过滤（见上方注释）
        _guarded(stf(_upcoming_reminders)(timezone.now(), ctx)),
        _guarded(stf(_client_count)()),
        _guarded(stf(_contract_count)()),
        _guarded(stf(_contract_trend)(timezone.localdate() - timedelta(days=365))),
    )

    case_type_dist, active_case_count = case_type_dist_and_count
    monthly_fee, fee_trend = fee_stats

    return {
        "client_count": client_count,
        "contract_count": contract_count,
        "case_count": active_case_count,
        "monthly_fee": str(monthly_fee),
        "case_trend": case_trend,
        "contract_trend": contract_trend,
        "fee_trend": fee_trend,
        "case_type_distribution": case_type_dist,
        "case_status_distribution": case_status_dist,
        "upcoming_reminders": upcoming_reminders,
        "overdue_count": reminder_counts["overdue_count"],
        "today_count": reminder_counts["today_count"],
    }
