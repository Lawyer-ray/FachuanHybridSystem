"""Agent 运行统计 —— 成本、耗时与失败率的聚合查询。

回答运营/管理最关心的三类问题：

- 这个律师 / 这个律所本月花了多少 token？
- 一次回答平均多久，失败率多少？
- 哪个模型用得多？

口径说明：
- token 由 pi 上报（`usage` 事件），一轮里工具循环会产出多段 assistant，
  这里累加的是**该轮全部 assistant 段**之和，与 provider 计费口径一致。
- 取消与出错同样计数（那些轮也消耗了 token），`status` 区分三态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from ..models import AgentRun

DEFAULT_DAYS = 30


@dataclass(slots=True)
class UsageSummary:
    """一段时间内的汇总。"""

    runs: int
    ok_runs: int
    error_runs: int
    cancelled_runs: int
    input_tokens: int
    output_tokens: int
    tool_calls: int
    avg_duration_ms: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def error_rate(self) -> float:
        return round(self.error_runs / self.runs, 4) if self.runs else 0.0


def _window_start(days: int) -> datetime:
    return timezone.now() - timedelta(days=max(1, days))


def summarize(
    *,
    user_id: int | None = None,
    days: int = DEFAULT_DAYS,
    session_id: str | None = None,
) -> UsageSummary:
    """按用户 / 会话 / 时间窗汇总。

    Args:
        user_id: 只看某人的；``None`` 表示全部（调用方须自行做权限判定）。
        days: 回看天数。
        session_id: 只看某个会话。
    """
    queryset = AgentRun.objects.filter(created_at__gte=_window_start(days))
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    if session_id is not None:
        queryset = queryset.filter(session__session_id=session_id)

    agg = queryset.aggregate(
        runs=Count("id"),
        ok_runs=Count("id", filter=Q(status=AgentRun.Status.OK)),
        error_runs=Count("id", filter=Q(status=AgentRun.Status.ERROR)),
        cancelled_runs=Count("id", filter=Q(status=AgentRun.Status.CANCELLED)),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        tool_calls=Sum("tool_calls"),
        total_duration=Sum("duration_ms"),
    )
    runs = int(agg["runs"] or 0)
    total_duration = int(agg["total_duration"] or 0)
    return UsageSummary(
        runs=runs,
        ok_runs=int(agg["ok_runs"] or 0),
        error_runs=int(agg["error_runs"] or 0),
        cancelled_runs=int(agg["cancelled_runs"] or 0),
        input_tokens=int(agg["input_tokens"] or 0),
        output_tokens=int(agg["output_tokens"] or 0),
        tool_calls=int(agg["tool_calls"] or 0),
        avg_duration_ms=int(total_duration / runs) if runs else 0,
    )


def daily_series(
    *,
    user_id: int | None = None,
    days: int = DEFAULT_DAYS,
) -> list[dict[str, Any]]:
    """按天的时间序列（前端画趋势用）。无记录的日期不补零。"""
    queryset = AgentRun.objects.filter(created_at__gte=_window_start(days))
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    rows = (
        queryset.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            errors=Count("id", filter=Q(status=AgentRun.Status.ERROR)),
        )
        .order_by("day")
    )
    return [
        {
            "day": row["day"].isoformat() if row["day"] else "",
            "runs": int(row["runs"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "errors": int(row["errors"] or 0),
        }
        for row in rows
    ]


def by_model(*, user_id: int | None = None, days: int = DEFAULT_DAYS) -> list[dict[str, Any]]:
    """按模型分组（看哪个模型贵、哪个用得多）。"""
    queryset = AgentRun.objects.filter(created_at__gte=_window_start(days))
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    rows = (
        queryset.values("model")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
        )
        .order_by("-runs")
    )
    return [
        {
            "model": row["model"] or "(未记录)",
            "runs": int(row["runs"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
        }
        for row in rows
    ]
