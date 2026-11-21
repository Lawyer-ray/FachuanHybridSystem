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

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, NullIf, TruncDate
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
    #: 缓存命中 / 写入 token 汇总。
    #:
    #: **为什么单列而不并进 input_tokens**：每轮的 ``cacheRead`` 是那次 API
    #: 调用重读的累计前缀，逐消息累加会严重虚高。它只用来回答「缓存帮了多少」
    #: 这个独立问题（见 :attr:`cache_hit_rate`），不参与成本口径。
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: 本月累计 token（预算口径，P1-8b）
    month_tokens: int = 0
    #: 月度预算上限（env 未配置为 0=不限）
    budget_tokens: int = 0
    #: 用量达预算 80% 以上时提醒
    budget_warn: bool = False

    @property
    def total_tokens(self) -> int:
        """计费口径的总 token（**不含** ``cache_read``）。

        为什么不计 cacheRead：它是重读的累计前缀，计进来会让「这个律师本月
        花了多少」虚高数倍，与 provider 账单对不上。要评估缓存收益请用
        :attr:`cache_hit_rate`。

        为什么**计** cacheWrite：缓存写入是真实计费的（且通常比普通输入更贵），
        不算进去就低估了「前缀变化导致的成本突增」——那正是本改造要监测的东西。
        """
        return self.input_tokens + self.output_tokens + self.cache_write_tokens

    @property
    def cache_hit_rate(self) -> float:
        """输入侧缓存命中率（0.0 – 1.0）。

        口径：``cacheRead / (input + cacheRead + cacheWrite)``。
        分母是「本次请求实际处理的全部输入侧 token」，分子是走缓存的部分。

        这个数字是法穿核心设计（AGENTS.md 逐轮字节稳定 → 命中 prompt cache）
        的**唯一验证手段**：低于预期就说明有东西在每轮改写系统提示词前缀
        （记忆快照漂移 / 工具集抖动 / 模型切换）。
        """
        denominator = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        if denominator <= 0:
            return 0.0
        return round(self.cache_read_tokens / denominator, 4)

    @property
    def error_rate(self) -> float:
        return round(self.error_runs / self.runs, 4) if self.runs else 0.0


def _window_start(days: int) -> datetime:
    return timezone.now() - timedelta(days=max(1, days))


def _runs_in_window(*, user_id: int | None, days: int) -> QuerySet[AgentRun]:
    """时间窗 + 可选用户过滤的公共 queryset（三个聚合入口同口径）。"""
    queryset = AgentRun.objects.filter(created_at__gte=_window_start(days))
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    return queryset


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
    queryset = _runs_in_window(user_id=user_id, days=days)
    if session_id is not None:
        queryset = queryset.filter(session__session_id=session_id)

    agg = queryset.aggregate(
        runs=Count("id"),
        ok_runs=Count("id", filter=Q(status=AgentRun.Status.OK)),
        error_runs=Count("id", filter=Q(status=AgentRun.Status.ERROR)),
        cancelled_runs=Count("id", filter=Q(status=AgentRun.Status.CANCELLED)),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        cache_read_tokens=Sum("cache_read_tokens"),
        cache_write_tokens=Sum("cache_write_tokens"),
        tool_calls=Sum("tool_calls"),
        total_duration=Sum("duration_ms"),
    )
    runs = int(agg["runs"] or 0)
    total_duration = int(agg["total_duration"] or 0)

    # ── 月度预算口径（P1-8b）：本月累计 token；env 配置预算后 80% 提醒 ──
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_qs = AgentRun.objects.filter(created_at__gte=month_start)
    if user_id is not None:
        month_qs = month_qs.filter(user_id=user_id)
    month_agg = month_qs.aggregate(
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        cache_write_tokens=Sum("cache_write_tokens"),
    )
    # 预算口径与 total_tokens 一致：含 output 与 cacheWrite，**不含** cacheRead
    month_tokens = (
        int(month_agg["input_tokens"] or 0)
        + int(month_agg["output_tokens"] or 0)
        + int(month_agg["cache_write_tokens"] or 0)
    )
    budget_tokens = int(os.environ.get("FACHUAN_AGENT_MONTHLY_TOKEN_BUDGET", "0") or 0)
    budget_warn = bool(budget_tokens > 0 and month_tokens >= budget_tokens * 0.8)

    return UsageSummary(
        runs=runs,
        ok_runs=int(agg["ok_runs"] or 0),
        error_runs=int(agg["error_runs"] or 0),
        cancelled_runs=int(agg["cancelled_runs"] or 0),
        input_tokens=int(agg["input_tokens"] or 0),
        output_tokens=int(agg["output_tokens"] or 0),
        cache_read_tokens=int(agg["cache_read_tokens"] or 0),
        cache_write_tokens=int(agg["cache_write_tokens"] or 0),
        tool_calls=int(agg["tool_calls"] or 0),
        avg_duration_ms=int(total_duration / runs) if runs else 0,
        month_tokens=month_tokens,
        budget_tokens=budget_tokens,
        budget_warn=budget_warn,
    )


def daily_series(
    *,
    user_id: int | None = None,
    days: int = DEFAULT_DAYS,
) -> list[dict[str, Any]]:
    """按天的时间序列（前端画趋势用）。无记录的日期不补零。"""
    queryset = _runs_in_window(user_id=user_id, days=days)
    rows = (
        queryset.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cache_read_tokens=Sum("cache_read_tokens"),
            cache_write_tokens=Sum("cache_write_tokens"),
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
            "cache_read_tokens": int(row["cache_read_tokens"] or 0),
            "cache_write_tokens": int(row["cache_write_tokens"] or 0),
            "errors": int(row["errors"] or 0),
        }
        for row in rows
    ]


def by_agent(*, user_id: int | None = None, days: int = DEFAULT_DAYS) -> list[dict[str, Any]]:
    """按 agent 后端分组（看每个 agent 花了多少、跑了多少轮）。

    ## 为什么需要它（与 ``by_model`` 的分工）

    ``by_model`` 回答「哪个模型贵」。多 agent 上线后，同一个模型可能被两个 agent
    同时用（例如 pi 和 dsh 都配 ``kimi-2.6``），那时按模型聚合根本分不清钱是谁花
    的——这是引入 ``AgentRun.agent_kind`` 的直接原因。

    两个维度不互相替代：律师问「换 dsh 到底值不值」看这里，问「glm53 比 kimi 便宜
    多少」看 ``by_model``。

    ## 空串归 pi

    引入 ``agent_kind`` 之前的历史记录该字段为空。那时**只有** pi 在跑，所以归到
    pi 是符合事实的（与 ``AgentMessage.agent_kind`` 的「空串当 pi」同口径）。
    不做这个归一的话，报表上会多出一行「(未记录)」，看起来像有个神秘的第四个
    agent 在烧钱。
    """
    queryset = _runs_in_window(user_id=user_id, days=days)
    # **在 SQL 里就归一空串**，不能只改显示文案：`GROUP BY agent_kind` 会把
    # `""` 与 `"pi"` 分成两组，逐行改名会让报表出现**两行都叫 pi** 的重复项，
    # 而它们的 token 各自只算了一半。Coalesce+NullIf 让数据库把它们当同一组。
    normalized = Coalesce(NullIf("agent_kind", Value("")), Value("pi"))
    rows = (
        queryset.annotate(agent_backend=normalized)
        .values("agent_backend")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cache_read_tokens=Sum("cache_read_tokens"),
            cache_write_tokens=Sum("cache_write_tokens"),
            failed=Count("id", filter=Q(status=AgentRun.Status.ERROR)),
            cancelled=Count("id", filter=Q(status=AgentRun.Status.CANCELLED)),
        )
        .order_by("-runs")
    )
    result = []
    for row in rows:
        input_tokens = int(row["input_tokens"] or 0)
        output_tokens = int(row["output_tokens"] or 0)
        cache_read = int(row["cache_read_tokens"] or 0)
        cache_write = int(row["cache_write_tokens"] or 0)
        denominator = input_tokens + cache_read + cache_write
        result.append(
            {
                "agent_kind": row["agent_backend"],
                "runs": int(row["runs"] or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                # 与 ``UsageSummary.total_tokens`` 同口径：含 output 与 cacheWrite，
                # **不含** cacheRead（重读的前缀计进去会让「谁花了多少」虚高数倍）。
                "total_tokens": input_tokens + output_tokens + cache_write,
                "cache_hit_rate": round(cache_read / denominator, 4) if denominator else 0.0,
                # 失败/中止单独计：多答时一个 agent 挂掉不该让整轮看起来失败，
                # 但运营要知道是哪个后端不稳。
                "failed_runs": int(row["failed"] or 0),
                "cancelled_runs": int(row["cancelled"] or 0),
            }
        )
    return result


def by_model(*, user_id: int | None = None, days: int = DEFAULT_DAYS) -> list[dict[str, Any]]:
    """按模型分组（看哪个模型贵、哪个用得多）。"""
    queryset = _runs_in_window(user_id=user_id, days=days)
    rows = (
        queryset.values("model")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cache_read_tokens=Sum("cache_read_tokens"),
            cache_write_tokens=Sum("cache_write_tokens"),
        )
        .order_by("-runs")
    )
    result = []
    for row in rows:
        input_tokens = int(row["input_tokens"] or 0)
        output_tokens = int(row["output_tokens"] or 0)
        cache_read = int(row["cache_read_tokens"] or 0)
        cache_write = int(row["cache_write_tokens"] or 0)
        denominator = input_tokens + cache_read + cache_write
        result.append(
            {
                "model": row["model"] or "(未记录)",
                "runs": int(row["runs"] or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                # 逐模型看命中率最有意义：不同 provider 的缓存策略差别很大
                "cache_hit_rate": round(cache_read / denominator, 4) if denominator else 0.0,
            }
        )
    return result


def by_provider(*, user_id: int | None = None, days: int = DEFAULT_DAYS) -> list[dict[str, Any]]:
    """按**平台**分组（哪个网关/平台花钱最多）。

    ## 与 by_model / by_agent 的分工

    - ``by_model``：哪个模型贵；
    - ``by_agent``：哪个 agent 后端贵；
    - ``by_provider``：钱花在**哪个平台**上（律所网关 / 别的服务商）。同一个模型可能由
      多个平台提供，同一个平台也会被多个 backend 用——三者互不替代。

    ## 空串显示为「未知」，不猜

    ``provider`` 字段是 2026-11-21 才加的（成本归属整改），历史行必然为空。这里**不按
    默认平台回填**：那会把别的平台的账算到它头上。报表里如实显示「未知」并保留一行，
    让运维一眼看出「这条数据是什么时候开始有的」。
    """
    queryset = _runs_in_window(user_id=user_id, days=days)
    normalized = Coalesce(NullIf("provider", Value("")), Value("未知"))
    rows = (
        queryset.annotate(provider_name=normalized)
        .values("provider_name")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cache_read_tokens=Sum("cache_read_tokens"),
            cache_write_tokens=Sum("cache_write_tokens"),
            failed=Count("id", filter=Q(status=AgentRun.Status.ERROR)),
        )
        .order_by("-runs")
    )
    result = []
    for row in rows:
        input_tokens = int(row["input_tokens"] or 0)
        output_tokens = int(row["output_tokens"] or 0)
        cache_read = int(row["cache_read_tokens"] or 0)
        cache_write = int(row["cache_write_tokens"] or 0)
        result.append(
            {
                "provider": row["provider_name"],
                "runs": int(row["runs"] or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                # 与 UsageSummary.total_tokens 同口径：含 output 与 cacheWrite，不含 cacheRead
                "total_tokens": input_tokens + output_tokens + cache_write,
                "failed_runs": int(row["failed"] or 0),
            }
        )
    return result
