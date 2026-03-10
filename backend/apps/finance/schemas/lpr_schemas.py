"""LPR相关API Schema定义.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from ninja import Field, Schema


class LPRRateSchema(Schema):
    """LPR利率数据Schema."""

    id: int
    effective_date: date
    rate_1y: Decimal = Field(..., description="一年期LPR(%)")
    rate_5y: Decimal = Field(..., description="五年期LPR(%)")
    source: str = Field("", description="数据来源")
    is_auto_synced: bool = Field(False, description="是否自动同步")
    created_at: str
    updated_at: str


class LPRRateListResponse(Schema):
    """LPR利率列表响应."""

    items: list[LPRRateSchema]
    total: int


class LPRSyncRequest(Schema):
    """LPR同步请求."""

    force: bool = Field(False, description="强制同步，忽略缓存")


class LPRSyncResponse(Schema):
    """LPR同步响应."""

    success: bool
    message: str
    created: int = Field(0, description="新增记录数")
    updated: int = Field(0, description="更新记录数")
    skipped: int = Field(0, description="跳过记录数")


class LPRSyncStatusResponse(Schema):
    """LPR同步状态响应."""

    latest_rate_date: date | None
    total_records: int
    auto_synced_records: int
    manual_records: int


class PrincipalChangeSchema(Schema):
    """本金变动Schema."""

    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    principal: Decimal = Field(..., description="本金金额")


class InterestCalculateRequest(Schema):
    """利息计算请求."""

    start_date: date | None = Field(None, description="开始日期（固定本金模式必填）")
    end_date: date | None = Field(None, description="结束日期（固定本金模式必填）")
    principal: Decimal | None = Field(None, description="本金（固定本金模式必填）")
    rate_type: Literal["1y", "5y"] = Field("1y", description="利率类型")
    year_days: int = Field(360, description="年基准天数(360/365/0实际天数)")
    multiplier: Decimal = Field(Decimal("1"), description="利率倍数")
    date_inclusion: Literal["both", "start_only", "end_only", "neither"] = Field(
        "both", description="日期计算方式: both=均计算在内, start_only=仅起始日期, end_only=仅截止日期, neither=均不计算"
    )
    principal_changes: list[PrincipalChangeSchema] | None = Field(
        None, description="本金变动列表（如提供则使用变动本金计算，此时不需要start_date/end_date/principal）"
    )


class CalculationPeriodSchema(Schema):
    """计算分段明细Schema."""

    start_date: date
    end_date: date
    principal: Decimal
    rate: Decimal
    days: int
    year_days: int
    interest: Decimal


class InterestCalculateResponse(Schema):
    """利息计算响应."""

    success: bool
    total_interest: Decimal | None = None
    total_principal: Decimal | None = None
    total_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    periods: list[CalculationPeriodSchema] | None = None
    message: str | None = None
    code: str | None = None
