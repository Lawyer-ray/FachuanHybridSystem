"""仪表盘聚合统计 API"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
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
async def get_dashboard_stats(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """返回仪表盘聚合统计数据。

    9 条独立 DB 查询的并发编排（asyncio.gather + Semaphore(4)）与读范围口径
    都在 ``DashboardService.agather_payload`` 内，本层只构造请求上下文后转发。

    S23-05（2026-11-23 二轮审计）：原实现由本函数 import service 模块的 9 个
    ``_`` 前缀私有查询函数自行并发（同时留下一个从未使用的 ``DashboardService()``
    实例），跨层绑死私有符号、读范围口径也无法在 service 内统一加门禁；
    现在改为只依赖 service 的公开方法。
    """
    from apps.core.security import get_request_access_context
    from apps.core.services.dashboard_service import DashboardService

    # 安全审计（2026-10-19）：ctx 按请求构造后传入 service（提醒列表在其内部按读范围过滤）。
    ctx = await sync_to_async(get_request_access_context)(request)
    return await DashboardService().agather_payload(ctx)
