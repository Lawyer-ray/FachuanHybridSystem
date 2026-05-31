"""仪表盘聚合统计 API"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.http import HttpRequest
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
def get_dashboard_stats(request: HttpRequest) -> dict[str, Any]:
    """返回仪表盘聚合统计数据。"""
    from apps.core.services.dashboard_service import DashboardService

    service = DashboardService()
    stats = service.get_stats()
    stats["monthly_fee"] = str(stats["monthly_fee"])
    return stats
