"""LPR 利率/利息计算 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_lpr_rates(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """获取 LPR 利率列表。日期格式: YYYY-MM-DD。"""
    params: dict[str, Any] = {"limit": limit}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return client.get("/lpr/rates", params=params)  # type: ignore[no-any-return]


def get_latest_lpr_rate() -> dict[str, Any]:
    """获取最新 LPR 利率。"""
    return client.get("/lpr/rates/latest")  # type: ignore[no-any-return]


def calculate_interest(
    principal: float,
    start_date: str,
    end_date: str,
    rate_addition: float = 0.0,
    rate_multiplier: float = 1.0,
) -> dict[str, Any]:
    """计算 LPR 利息。start_date/end_date 格式: YYYY-MM-DD。rate_addition: 加点基点，rate_multiplier: 倍率。"""
    return client.post(  # type: ignore[no-any-return]
        "/lpr/calculate",
        json={
            "principal": principal,
            "start_date": start_date,
            "end_date": end_date,
            "rate_addition": rate_addition,
            "rate_multiplier": rate_multiplier,
        },
    )


def sync_lpr_rates() -> dict[str, Any]:
    """手动触发 LPR 利率同步（从央行网站抓取）。需要管理员权限。"""
    return client.post("/lpr/sync", json={})  # type: ignore[no-any-return]


def get_lpr_sync_status() -> dict[str, Any]:
    """获取 LPR 利率同步状态，包含最新利率日期和记录统计。"""
    return client.get("/lpr/sync/status")  # type: ignore[no-any-return]
