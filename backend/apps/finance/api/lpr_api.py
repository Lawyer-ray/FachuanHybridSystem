"""LPR相关API端点."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.http import HttpRequest
from ninja import Router

from apps.core.exceptions import ValidationException
from apps.core.security.auth import JWTOrSessionAuth
from apps.finance.schemas.lpr_schemas import (
    InterestCalculateRequest,
    InterestCalculateResponse,
    LPRRateListResponse,
    LPRRateSchema,
    LPRSyncRequest,
    LPRSyncResponse,
    LPRSyncStatusResponse,
    MortgageAmortizeRequest,
    MortgageAmortizeResponse,
    MortgageDefaultRequest,
    MortgageDefaultResponse,
)
from apps.finance.services.lpr import PrincipalPeriod

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

router = Router(tags=["LPR利率"])


@router.get("/rates", response=LPRRateListResponse, auth=JWTOrSessionAuth())
def list_lpr_rates(  # pragma: no cover
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
    from apps.finance.services.lpr.rate_service import LPRRateService

    rate_service = LPRRateService()
    items = rate_service.get_rate_history(start_date=start_date, end_date=end_date, limit=limit)
    total = len(items)

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
def get_latest_lpr_rate(request: HttpRequest) -> LPRRateSchema:  # pragma: no cover
    """获取最新LPR利率.

    Args:
        request: HTTP请求

    Returns:
        最新LPR利率
    """
    from apps.finance.services.lpr.rate_service import LPRRateService

    try:
        rate = LPRRateService().get_latest_rate()
    except Exception:
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
def sync_lpr_rates(  # pragma: no cover
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
    user: User = request.user

    # 检查权限
    if not user.is_staff:
        from apps.core.exceptions import PermissionDeniedException

        raise PermissionDeniedException(message="需要管理员权限才能同步LPR数据", code="PERMISSION_DENIED")

    logger.info(f"[LPRSync] User {user.id} triggered manual LPR sync")

    try:
        from apps.core.tasking import submit_task

        task_id = submit_task(
            "apps.finance.tasks.sync_lpr_rates",
            task_name=f"lpr_manual_sync_user_{user.id}",
            timeout=300,
        )

        return LPRSyncResponse(
            success=True,
            message="LPR数据同步任务已提交，请稍后查看结果",
            task_id=task_id,
        )

    except Exception as e:
        logger.error(f"[LPRSync] Failed to submit sync task: {e}")
        return LPRSyncResponse(
            success=False,
            message=f"提交同步任务失败: {e!s}",
        )


@router.get("/sync/status", response=LPRSyncStatusResponse, auth=JWTOrSessionAuth())
def get_sync_status(request: HttpRequest) -> LPRSyncStatusResponse:  # pragma: no cover
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
def calculate_interest(  # pragma: no cover
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

    # LPR 模式下自动同步过期数据
    # sync_if_needed 内部可能调用 Playwright 同步 I/O（最长 60s+），
    # 使用线程池 + 超时避免阻塞请求太长时间
    sync_info = None
    if data.rate_mode == "lpr":
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FutureTimeout

        from apps.finance.services.lpr import LPRSyncService

        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="lpr-sync") as pool:
                future = pool.submit(LPRSyncService().sync_if_needed)
                sync_result = future.result(timeout=120)
            if sync_result["synced"]:
                r = sync_result["sync_result"]
                sync_info = f"LPR数据已自动同步（新增{r.get('created', 0)}条）"
            elif sync_result["error"]:
                logger.warning("[LPRCalc] Auto-sync failed, using existing data: %s", sync_result["error"])
        except FutureTimeout:
            logger.warning("[LPRCalc] Auto-sync timed out after 120s, using existing data")
        except Exception as e:
            logger.warning("[LPRCalc] Auto-sync error, using existing data: %s", e)

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
        sync_info=sync_info,
    )


@router.post("/amortize", response=MortgageAmortizeResponse, auth=JWTOrSessionAuth())
def amortize_mortgage(  # pragma: no cover
    request: HttpRequest,
    data: MortgageAmortizeRequest,
) -> MortgageAmortizeResponse:
    """房贷摊销计算（等额本息/等额本金还款计划）.

    Args:
        request: HTTP请求
        data: 摊销计算参数

    Returns:
        还款计划
    """
    from apps.finance.services.calculator import MortgageDefaultCalculator

    try:
        calculator = MortgageDefaultCalculator()
        # 复用违约计算器生成纯计划（无流水、截止日在首期前只截利息，故传截止日=首期前模拟纯计划）
        result = calculator.calculate(
            principal=data.principal,
            start_date=data.start_date,
            term_months=data.term_months,
            repayment_method=data.repayment_method,
            payment_day=data.payment_day,
            rate_mode=data.rate_mode,
            fixed_rate=data.fixed_rate,
            lpr_type=data.lpr_type,
            basis_points=data.basis_points,
            repricing_day=data.repricing_day,
            claim_date=date.max,
        )
    except ValidationException as e:
        return MortgageAmortizeResponse(success=False, message=e.message, code=e.code)

    schedule = [
        {
            "period_no": r.period_no,
            "due_date": r.due_date,
            "monthly_payment": r.monthly_payment,
            "principal_part": r.principal_part,
            "interest_part": r.interest_part,
            "annual_rate": r.annual_rate,
            "remaining_principal": r.remaining_principal,
            "rescheduled": r.rescheduled,
        }
        for r in result.schedule_rows
    ]
    return MortgageAmortizeResponse(
        success=True,
        schedule_rows=schedule,
        first_due_date=result.meta.get("first_due_date", ""),
        total_periods=len(schedule),
    )


@router.post("/mortgage-default-calculate", response=MortgageDefaultResponse, auth=JWTOrSessionAuth())
def mortgage_default_calculate(  # pragma: no cover
    request: HttpRequest,
    data: MortgageDefaultRequest,
) -> MortgageDefaultResponse:
    """房贷逾期违约债权计算（银行诉讼场景）.

    基于等额本息/等额本金摊销 + 还款流水冲抵，输出：
    - 诉讼请求金额汇总（剩余本金/未付利息/罚息/复利/合计/日增金额）
    - 逐期违约明细（含每笔还款冲抵明细）
    - 重排后的还款计划对照表

    Args:
        request: HTTP请求
        data: 违约债权计算参数

    Returns:
        计算结果
    """
    from apps.finance.services.calculator import MortgageDefaultCalculator, PaymentRecord

    try:
        calculator = MortgageDefaultCalculator()
        result = calculator.calculate(
            principal=data.principal,
            start_date=data.start_date,
            term_months=data.term_months,
            repayment_method=data.repayment_method,
            payment_day=data.payment_day,
            rate_mode=data.rate_mode,
            fixed_rate=data.fixed_rate,
            lpr_type=data.lpr_type,
            basis_points=data.basis_points,
            repricing_day=data.repricing_day,
            penalty_mode=data.penalty_mode,
            penalty_multiplier=data.penalty_multiplier,
            penalty_rate=data.penalty_rate,
            compound_on_interest=data.compound_on_interest,
            compound_on_penalty=data.compound_on_penalty,
            year_days=data.year_days,
            allocation_order=data.allocation_order,
            prepayment_handling=data.prepayment_handling,
            payments=[
                PaymentRecord(
                    payment_date=p.payment_date,
                    amount=p.amount,
                    payment_type=p.payment_type,
                    note=p.note,
                )
                for p in data.payments
            ],
            claim_date=data.claim_date,
        )
    except ValidationException as e:
        return MortgageDefaultResponse(success=False, message=e.message, code=e.code)

    return MortgageDefaultResponse(success=True, **result.to_dict())
