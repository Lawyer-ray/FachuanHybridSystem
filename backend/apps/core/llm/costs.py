"""LLM 调用成本估算与聚合。

基于 LLMCallRecord 审计数据,按 backend/model/caller 聚合用量,并基于
可注入的定价表估算成本。定价表单位为「美元 / 每百万 token」,
键为模型名(支持精确匹配与子串/前缀匹配),另支持 "__default__" 兜底。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# 模型 -> (输入价格 /100万 token, 输出价格 /100万 token),单位 USD。
# 仅内置少量已知价格作为示例,实际生产应注入按需维护的定价表。
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen-plus": (0.40, 1.20),
    "moonshot-v1": (12.00, 12.00),
    "kimi-k2": (0.60, 2.50),
    "__default__": (0.0, 0.0),
}


def price_for_model(model: str, pricing: Mapping[str, tuple[float, float]] = DEFAULT_PRICING) -> tuple[float, float]:
    """解析模型的 (输入, 输出) 每百万 token 价格;精确匹配失败时做前缀/子串匹配。"""
    key = (model or "").strip().lower()
    if key in pricing:
        return pricing[key]
    for name, prices in pricing.items():
        if name != "__default__" and key.startswith(name):
            return prices
    for name, prices in pricing.items():
        if name != "__default__" and name in key:
            return prices
    return pricing.get("__default__", (0.0, 0.0))


def estimate_cost(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: Mapping[str, tuple[float, float]] = DEFAULT_PRICING,
) -> float:
    """按模型单价估算一次调用成本(USD)。"""
    input_price, output_price = price_for_model(model, pricing)
    return (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price


def aggregate_costs(
    group_by: Sequence[str] = ("backend", "model"),
    *,
    pricing: Mapping[str, tuple[float, float]] = DEFAULT_PRICING,
    **filters: Any,
) -> list[dict[str, Any]]:
    """按指定维度聚合成功调用的用量与估算成本。

    ``filters`` 直接传给 queryset(如 backend=, model=, caller=, success=, 时间范围)。
    返回按 cost 降序的逐组统计。
    """
    from django.db.models import Avg, Count, Sum

    from apps.core.models import LLMCallRecord

    qs = LLMCallRecord.objects.filter(success=True, **filters)
    rows = (
        qs.values(*group_by)
        .annotate(
            call_count=Count("id"),
            sum_prompt_tokens=Sum("prompt_tokens"),
            sum_completion_tokens=Sum("completion_tokens"),
            sum_total_tokens=Sum("total_tokens"),
            avg_duration_ms=Avg("duration_ms"),
        )
        .order_by("-sum_total_tokens")
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        model = str(row.get("model", "") or "")
        input_price, output_price = price_for_model(model, pricing)
        cost = (float(row["sum_prompt_tokens"]) / 1_000_000) * input_price
        cost += (float(row["sum_completion_tokens"]) / 1_000_000) * output_price
        results.append(
            {
                **row,
                "estimated_cost_usd": round(cost, 4),
            }
        )
    results.sort(key=lambda r: r["estimated_cost_usd"], reverse=True)
    return results


async def aaggregate_costs(
    group_by: Sequence[str] = ("backend", "model"),
    *,
    pricing: Mapping[str, tuple[float, float]] = DEFAULT_PRICING,
    **filters: Any,
) -> list[dict[str, Any]]:
    """异步版 ``aggregate_costs``,用 ``sync_to_async`` 规避 ORM 同步调用。"""
    from asgiref.sync import sync_to_async

    return await sync_to_async(aggregate_costs)(group_by, pricing=pricing, **filters)
