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
    """
    import asyncio

    from asgiref.sync import sync_to_async
    from apps.workbench.services.dashboard_service import DashboardService

    service = DashboardService()

    # thread_sensitive=False 让每个调用在独立线程中执行，实现真正并行
    stf = sync_to_async(thread_sensitive=False)

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
        stf(service._case_type_stats)(),
        stf(service._case_trend)(timezone.localdate() - timedelta(days=365)),
        stf(service._case_status_distribution)(),
        stf(service._fee_stats)(
            timezone.localdate().replace(day=1), timezone.localdate(), timezone.localdate() - timedelta(days=365)
        ),
        stf(service._reminder_counts)(timezone.now()),
        stf(service._upcoming_reminders)(timezone.now()),
        stf(service._client_count)(),
        stf(service._contract_count)(),
        stf(service._contract_trend)(timezone.localdate() - timedelta(days=365)),
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
