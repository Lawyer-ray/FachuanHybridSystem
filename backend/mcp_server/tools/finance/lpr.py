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
    """获取最新 LPR 报价（1年期/5年期）——利息计算前查基准利率。"""
    return client.get("/lpr/rates/latest")  # type: ignore[no-any-return]


def calculate_interest(
    principal: float,
    start_date: str,
    end_date: str,
    rate_mode: str = "lpr",
    rate_type: str = "1y",
    multiplier: float = 1.0,
    custom_rate_value: float | None = None,
    custom_rate_unit: str = "percent",
    year_days: int = 360,
    date_inclusion: str = "both",
) -> dict[str, Any]:
    """按 LPR 或自定义利率计算利息（固定本金模式）。

    历史版本的 rate_addition/rate_multiplier 参数从未生效（REST schema 没有
    这些字段,pydantic 静默丢弃——「LPR 四倍」会按一倍算）,2026-10-25 参数级
    契约审计后对齐后端 ``InterestCalculateRequest``。

    Args:
        principal: 本金（元）。
        start_date/end_date: 起止日期,格式 YYYY-MM-DD。
        rate_mode: lpr=按 LPR 报价,custom=自定义利率。
        rate_type: LPR 期限品种: 1y / 5y（LPR 模式）。
        multiplier: 利率倍数（LPR 模式;如 4 倍上浮传 4）。
        custom_rate_value: 自定义利率数值（custom 模式必填,如 5 配合
            custom_rate_unit=permille 表示千分之五）。
        custom_rate_unit: percent / permille / permyriad。
        year_days: 年基准天数: 360 / 365 / 0（按实际天数）。
        date_inclusion: 日期计算方式: both / start_only / end_only / neither。
    """
    return client.post(  # type: ignore[no-any-return]
        "/lpr/calculate",
        json={
            "principal": principal,
            "start_date": start_date,
            "end_date": end_date,
            "rate_mode": rate_mode,
            "rate_type": rate_type,
            "multiplier": multiplier,
            "custom_rate_value": custom_rate_value,
            "custom_rate_unit": custom_rate_unit,
            "year_days": year_days,
            "date_inclusion": date_inclusion,
        },
    )


def sync_lpr_rates() -> dict[str, Any]:
    """手动触发 LPR 利率同步（从央行网站抓取）。需要管理员权限。"""
    return client.post("/lpr/sync", json={})  # type: ignore[no-any-return]


def get_lpr_sync_status() -> dict[str, Any]:
    """获取 LPR 利率同步状态，包含最新利率日期和记录统计。"""
    return client.get("/lpr/sync/status")  # type: ignore[no-any-return]
