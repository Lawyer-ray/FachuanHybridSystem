"""
保险批量询价模块

提供并发查询所有保险公司报价的功能.
作为 CourtInsuranceClient 的 Mixin 使用.
"""

import asyncio
import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from .insurance_data import InsuranceCompany, PremiumResult

if TYPE_CHECKING:

    class _FetchPremiumHost(Protocol):
        async def fetch_premium(
            self,
            *,
            bearer_token: str,
            preserve_amount: Decimal,
            institution: str,
            corp_id: str,
            timeout: float | None = ...,
        ) -> PremiumResult: ...


logger = logging.getLogger("apps.automation")


class InsuranceBatchMixin:
    """保险批量查询 Mixin

    提供并发查询所有保险公司报价的方法.
    需要主类实现 fetch_premium 方法.
    """

    async def fetch_all_premiums(
        self: "_FetchPremiumHost",
        bearer_token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: list[InsuranceCompany],
        timeout: float | None = None,
    ) -> list[PremiumResult]:
        """
        并发查询所有保险公司报价

        使用 asyncio.gather 并发执行所有查询,单个查询失败不影响其他查询.

        Args:
            bearer_token: Bearer Token
            preserve_amount: 保全金额
            corp_id: 企业/法院 ID
            companies: 保险公司列表
            timeout: 超时时间(秒),默认使用 DEFAULT_TIMEOUT

        Returns:
            所有保险公司的报价结果列表
        """
        if not companies:
            logger.warning("保险公司列表为空,无法查询报价", extra={})
            return []

        logger.info(
            f"开始并发查询 {len(companies)} 家保险公司报价",
            extra={
                "action": "fetch_all_premiums_start",
                "preserve_amount": str(preserve_amount),
                "corp_id": corp_id,
                "total_companies": len(companies),
                "timeout": timeout,
            },
        )

        start_time = time.time()

        tasks: list[Any] = [
            self.fetch_premium(
                bearer_token=bearer_token,
                preserve_amount=preserve_amount,
                institution=company.c_code,
                corp_id=corp_id,
                timeout=timeout,
            )
            for company in companies
        ]

        results: list[PremiumResult | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_time = time.time() - start_time

        # 处理结果
        premium_results = _process_batch_results(results, companies)

        # 统计结果
        success_count = sum(1 for r in premium_results if r.status == "success")
        failed_count = len(premium_results) - success_count

        logger.info(
            "✅ 并发查询完成",
            extra={
                "action": "fetch_all_premiums_complete",
                "total_time_seconds": round(elapsed_time, 2),
                "total_companies": len(companies),
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": round(success_count / len(companies) * 100, 2) if companies else 0,
                "avg_time_per_company": round(elapsed_time / len(companies), 3) if companies else 0,
            },
        )

        return premium_results


def _process_batch_results(results: list[Any], companies: list[InsuranceCompany]) -> list[PremiumResult]:
    """处理批量查询结果"""
    premium_results: list[PremiumResult] = []

    for i, result in enumerate(results):
        company = companies[i]

        if isinstance(result, Exception):
            error_msg = f"查询异常: {result!s}"
            logger.error(
                f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                extra={
                    "action": "fetch_all_premiums_task_exception",
                    "company_name": company.c_name,
                    "company_code": company.c_code,
                    "error_type": type(result).__name__,
                    "error_message": str(result),
                },
                exc_info=result,
            )
            premium_results.append(
                PremiumResult(
                    company=company,
                    premium=None,
                    status="failed",
                    error_message=error_msg,
                    response_data=None,
                )
            )
        elif isinstance(result, PremiumResult):
            result.company.c_id = company.c_id
            result.company.c_name = company.c_name
            premium_results.append(result)
        else:
            error_msg = f"未知结果类型: {type(result)}"
            logger.error(
                f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                extra={
                    "action": "fetch_all_premiums_unknown_result",
                    "company_name": company.c_name,
                    "company_code": company.c_code,
                    "result_type": str(type(result)),
                },
            )
            premium_results.append(
                PremiumResult(
                    company=company,
                    premium=None,
                    status="failed",
                    error_message=error_msg,
                    response_data=None,
                )
            )

    return premium_results
