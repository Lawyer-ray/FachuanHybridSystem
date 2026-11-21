"""Agent 用量 API —— 成本 / 耗时汇总、按天趋势、按模型分布。

端点前缀：``/api/v1/agent``（用量子域）。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import UsageOut
from ..schemas.usage_schemas import UsageByAgentOut
from ..services.usage_stats import UsageSummary
from ..services.usage_stats import by_agent as usage_by_agent
from ..services.usage_stats import by_model as usage_by_model
from ..services.usage_stats import daily_series as usage_daily_series
from ..services.usage_stats import summarize as usage_summarize
from ._helpers import _current_user, _user_id

router = Router(tags=["Agent 用量"], auth=JWTOrSessionAuth())


def _to_usage(summary: UsageSummary) -> UsageOut:
    return UsageOut(
        runs=summary.runs,
        ok_runs=summary.ok_runs,
        error_runs=summary.error_runs,
        cancelled_runs=summary.cancelled_runs,
        input_tokens=summary.input_tokens,
        output_tokens=summary.output_tokens,
        total_tokens=summary.total_tokens,
        cache_read_tokens=summary.cache_read_tokens,
        cache_write_tokens=summary.cache_write_tokens,
        cache_hit_rate=summary.cache_hit_rate,
        tool_calls=summary.tool_calls,
        avg_duration_ms=summary.avg_duration_ms,
        error_rate=summary.error_rate,
        month_tokens=summary.month_tokens,
        budget_tokens=summary.budget_tokens,
        budget_warn=summary.budget_warn,
    )


@router.get("/usage", response=UsageOut)
async def get_usage(request: Any, days: int = 30) -> UsageOut:  # pragma: no cover
    """当前用户的成本与耗时汇总（超级用户可加 ``?all=true`` 看全所）。

    口径：token 由 pi 上报，一轮内工具循环的多段 assistant 逐段累加；
    取消与出错的轮次同样计入（那些轮也消耗了 token）。
    """
    user = _current_user(request)
    is_super = user is not None and getattr(user, "is_superuser", False)
    scope_user = None if (is_super and getattr(request, "GET", {}).get("all") == "true") else _user_id(request)
    summary = await sync_to_async(usage_summarize, thread_sensitive=True)(user_id=scope_user, days=days)
    return _to_usage(summary)


@router.get("/usage/daily", response=list[dict[str, Any]])
async def get_usage_daily(request: Any, days: int = 30) -> list[dict[str, Any]]:  # pragma: no cover
    """按天的成本趋势（前端画折线用）。"""
    return await sync_to_async(usage_daily_series, thread_sensitive=True)(user_id=_user_id(request), days=days)


@router.get("/usage/by-model", response=list[dict[str, Any]])
async def get_usage_by_model(request: Any, days: int = 30) -> list[dict[str, Any]]:  # pragma: no cover
    """按模型的用量分布。"""
    return await sync_to_async(usage_by_model, thread_sensitive=True)(user_id=_user_id(request), days=days)


@router.get("/usage/by-agent", response=list[UsageByAgentOut])
async def get_usage_by_agent(request: Any, days: int = 30) -> list[UsageByAgentOut]:  # pragma: no cover
    """按 agent 后端的成本归因（哪个后端跑了多少轮、花了多少 token）。

    权限口径与 ``/usage`` ``/usage/daily`` ``/usage/by-model`` 一致：只看当前用户。
    ``by_model`` 分不清「同一个模型被两个 agent 用时钱是谁花的」，这个端点回答它。
    空 ``agent_kind``（引入字段前的历史行）已在 SQL 侧归 ``pi``，不会多出一行
    「(未记录)」。
    """
    rows = await sync_to_async(usage_by_agent, thread_sensitive=True)(user_id=_user_id(request), days=days)
    return [UsageByAgentOut(**row) for row in rows]
