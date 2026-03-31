"""LPR相关API端点."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.http import HttpRequest
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth
from apps.finance.schemas.lpr_schemas import (
    InterestCalculateRequest,
    InterestCalculateResponse,
    LPRRateListResponse,
    LPRRateSchema,
    LPRSyncRequest,
    LPRSyncResponse,
    LPRSyncStatusResponse,
)
from apps.finance.services.lpr import PrincipalPeriod

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

router = Router(tags=["LPR利率"])


@router.get("/rates", response=LPRRateListResponse, auth=JWTOrSessionAuth())
def list_lpr_rates(
    request: HttpRequest,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
) -> LPRRateListResponse:
    """获取LPR利率列表.

    Args:
        request: HTTP请求
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        limit: 返回数量限制

    Returns:
        LPR利率列表
    """
    from apps.finance.models.lpr_rate import LPRRate

    queryset = LPRRate.objects.all()

    if start_date:
        queryset = queryset.filter(effective_date__gte=start_date)
    if end_date:
        queryset = queryset.filter(effective_date__lte=end_date)

    total = queryset.count()
    items = list(queryset[:limit])

    return LPRRateListResponse(
        items=[
            LPRRateSchema(
                id=item.id,
                effective_date=item.effective_date,
                rate_1y=item.rate_1y,
                rate_5y=item.rate_5y,
                source=item.source,
                is_auto_synced=item.is_auto_synced,
                created_at=item.created_at.isoformat(),
                updated_at=item.updated_at.isoformat(),
            )
            for item in items
        ],
        total=total,
    )


@router.get("/rates/latest", response=LPRRateSchema, auth=JWTOrSessionAuth())
def get_latest_lpr_rate(request: HttpRequest) -> LPRRateSchema:
    """获取最新LPR利率.

    Args:
        request: HTTP请求

    Returns:
        最新LPR利率
    """
    from apps.finance.models.lpr_rate import LPRRate

    rate = LPRRate.objects.first()
    if not rate:
        from apps.core.exceptions import NotFoundException

        raise NotFoundException(message="暂无LPR利率数据", code="LPR_RATE_NOT_FOUND")

    return LPRRateSchema(
        id=rate.id,
        effective_date=rate.effective_date,
        rate_1y=rate.rate_1y,
        rate_5y=rate.rate_5y,
        source=rate.source,
        is_auto_synced=rate.is_auto_synced,
        created_at=rate.created_at.isoformat(),
        updated_at=rate.updated_at.isoformat(),
    )


@router.post("/sync", response=LPRSyncResponse, auth=JWTOrSessionAuth())
def sync_lpr_rates(
    request: HttpRequest,
    data: LPRSyncRequest,
) -> LPRSyncResponse:
    """手动同步LPR数据.

    从央行官网获取最新LPR数据并同步到数据库。
    需要管理员权限。

    Args:
        request: HTTP请求
        data: 同步请求参数

    Returns:
        同步结果
    """
    user: User = request.user  # type: ignore[assignment]

    # 检查权限
    if not user.is_staff:
        from apps.core.exceptions import PermissionDeniedException

        raise PermissionDeniedException(message="需要管理员权限才能同步LPR数据", code="PERMISSION_DENIED")

    logger.info(f"[LPRSync] User {user.id} triggered manual LPR sync")

    try:
        from apps.finance.services.lpr_sync_service import LPRSyncService

        service = LPRSyncService()
        result = service.sync_latest()

        return LPRSyncResponse(
            success=True,
            message="LPR数据同步成功",
            created=result.get("created", 0),
            updated=result.get("updated", 0),
            skipped=result.get("skipped", 0),
        )

    except Exception as e:
        logger.error(f"[LPRSync] Manual sync failed: {e}")
        return LPRSyncResponse(
            success=False,
            message=f"同步失败: {e!s}",
        )


@router.get("/sync/status", response=LPRSyncStatusResponse, auth=JWTOrSessionAuth())
def get_sync_status(request: HttpRequest) -> LPRSyncStatusResponse:
    """获取LPR同步状态.

    Args:
        request: HTTP请求

    Returns:
        同步状态信息
    """
    from apps.finance.services.lpr import LPRSyncService

    service = LPRSyncService()
    status = service.get_sync_status()

    return LPRSyncStatusResponse(
        latest_rate_date=status.get("latest_rate_date"),
        total_records=status.get("total_records", 0),
        auto_synced_records=status.get("auto_synced_records", 0),
        manual_records=status.get("manual_records", 0),
    )


@router.post("/calculate", response=InterestCalculateResponse, auth=JWTOrSessionAuth())
def calculate_interest(
    request: HttpRequest,
    data: InterestCalculateRequest,
) -> InterestCalculateResponse:
    """计算LPR利息.

    支持固定本金和变动本金两种计算模式。

    Args:
        request: HTTP请求
        data: 计算请求参数

    Returns:
        计算结果或错误信息
    """
    from apps.finance.services.calculator import InterestCalculator

    calculator = InterestCalculator()

    # 检查是否使用变动本金
    if data.principal_changes:
        # 变动本金计算
        principal_periods = [
            PrincipalPeriod(
                start_date=p.start_date,
                end_date=p.end_date,
                principal=p.principal,
            )
            for p in data.principal_changes
        ]

        result = calculator.calculate_with_principal_changes(
            principal_periods=principal_periods,
            rate_type=data.rate_type,
            year_days=data.year_days,
            multiplier=data.multiplier,
            date_inclusion=data.date_inclusion,
            custom_rate_unit=data.custom_rate_unit if data.rate_mode == "custom" else None,
            custom_rate_value=data.custom_rate_value if data.rate_mode == "custom" else None,
        )
    else:
        # 固定本金计算 - 验证必需参数
        if data.start_date is None or data.end_date is None or data.principal is None:
            return InterestCalculateResponse(
                success=False,
                message="固定本金模式需要填写开始日期、结束日期和本金金额",
                code="MISSING_REQUIRED_FIELDS",
            )

        result = calculator.calculate(
            start_date=data.start_date,
            end_date=data.end_date,
            principal=data.principal,
            rate_type=data.rate_type,
            year_days=data.year_days,
            multiplier=data.multiplier,
            date_inclusion=data.date_inclusion,
            custom_rate_unit=data.custom_rate_unit if data.rate_mode == "custom" else None,
            custom_rate_value=data.custom_rate_value if data.rate_mode == "custom" else None,
        )

    return InterestCalculateResponse(
        success=True,
        total_interest=result.total_interest,
        total_principal=result.total_principal,
        total_days=result.total_days,
        start_date=result.start_date,
        end_date=result.end_date,
        periods=[
            {
                "start_date": p.start_date,
                "end_date": p.end_date,
                "principal": p.principal,
                "rate": p.rate,
                "rate_unit": getattr(p, "rate_unit", None),
                "days": p.days,
                "year_days": p.year_days,
                "interest": p.interest,
            }
            for p in result.periods
        ],
    )
