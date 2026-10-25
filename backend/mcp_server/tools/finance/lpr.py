"""LPR 利率/利息计算 MCP tools"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client

#: 枚举取值与后端 InterestCalculateRequest 的 Literal 同源(逐值对账测试)。
_RateModeL = Literal["lpr", "custom"]
_RateTypeL = Literal["1y", "5y"]
_RateUnitL = Literal["percent", "permille", "permyriad"]
_DateInclusionL = Literal["both", "start_only", "end_only", "neither"]
_YearDaysL = Literal[360, 365, 0]


def list_lpr_rates(
    start_date: Annotated[str | None, Field(description="起始日期(含),YYYY-MM-DD")] = None,
    end_date: Annotated[str | None, Field(description="截止日期(含),YYYY-MM-DD")] = None,
    limit: Annotated[int, Field(description="最多返回条数(默认 60,全量 25KB 超截断线)", ge=1)] = 60,
) -> dict[str, Any]:
    """获取 LPR 利率列表（默认最近 60 条,全量实测 25KB 超截断线）。日期格式: YYYY-MM-DD。

    Args:
        start_date: 可选,起始日期(含),YYYY-MM-DD。
        end_date: 可选,截止日期(含),YYYY-MM-DD。
        limit: 最多返回条数(默认 60;翻页语义见信封 truncated)。
    """
    params: dict[str, Any] = {"limit": limit + 1}  # limit+1 探测:知还有更多
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return client.get("/lpr/rates", params=params)  # type: ignore[no-any-return]


def get_latest_lpr_rate() -> dict[str, Any]:
    """获取最新 LPR 报价（1年期/5年期）——利息计算前查基准利率。"""
    return client.get("/lpr/rates/latest")  # type: ignore[no-any-return]


def calculate_interest(
    principal: Annotated[float, Field(description="本金(元)", gt=0)],
    start_date: Annotated[str, Field(description="起始日期,YYYY-MM-DD")],
    end_date: Annotated[str, Field(description="截止日期,YYYY-MM-DD")],
    rate_mode: Annotated[_RateModeL, Field(description="利率模式:lpr=按 LPR 报价 / custom=自定义利率")] = "lpr",
    rate_type: Annotated[_RateTypeL, Field(description="LPR 期限品种:1y / 5y(LPR 模式)")] = "1y",
    multiplier: Annotated[float, Field(description="利率倍数(LPR 模式;如 4 倍上浮传 4)", gt=0)] = 1.0,
    custom_rate_value: Annotated[float | None, Field(description="自定义利率数值(custom 模式必填,如 5 配合 custom_rate_unit=permille 表示千分之五)")] = None,
    custom_rate_unit: Annotated[_RateUnitL, Field(description="自定义利率单位:percent 百分之 / permille 千分之 / permyriad 万分之")] = "percent",
    year_days: Annotated[_YearDaysL, Field(description="年基准天数:360 / 365 / 0(按实际天数)")] = 360,
    date_inclusion: Annotated[_DateInclusionL, Field(description="日期计算方式:both 均计 / start_only 仅起始 / end_only 仅截止 / neither 均不计")] = "both",
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
        # LPR 模式下后端发现利率过期会先跑 Playwright 同步（服务端等待上限
        # 120s）——client 默认 60s 会先掐断,首日首算必失败。
        timeout=180,
    )


def sync_lpr_rates() -> dict[str, Any]:
    """手动触发 LPR 利率同步（Playwright 抓央行网站,需数十秒）。需要管理员权限。"""
    # 抓取走 Playwright,60s 默认超时不够;pi 侧 mcp.json timeout=200 兜住。
    return client.post("/lpr/sync", json={}, timeout=180)  # type: ignore[no-any-return]


def get_lpr_sync_status() -> dict[str, Any]:
    """获取 LPR 利率同步状态，包含最新利率日期和记录统计。"""
    return client.get("/lpr/sync/status")  # type: ignore[no-any-return]
