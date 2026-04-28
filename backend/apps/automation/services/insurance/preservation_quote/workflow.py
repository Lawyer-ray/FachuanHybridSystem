"""Business workflow orchestration."""

import logging
import time
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from apps.automation.models import QuoteStatus
from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.insurance.exceptions import ValidationError

from .client_facade import InsuranceClientFacade
from .repo import PreservationQuoteRepository
from .token_provider import BaoquanTokenProvider

logger = logging.getLogger("apps.automation")


class PreservationQuoteWorkflow:
    def __init__(
        self,
        *,
        repo: PreservationQuoteRepository,
        token_provider: BaoquanTokenProvider,
        client_facade: InsuranceClientFacade,
        insurance_client: CourtInsuranceClient,
    ) -> None:
        self.repo = repo
        self.token_provider = token_provider
        self.client_facade = client_facade
        self.insurance_client = insurance_client

    async def execute_quote(self, quote_id: int) -> dict[str, Any]:
        task_start_time = time.time()
        quote = await self.repo.get_quote_model(quote_id=quote_id)

        logger.info(
            "开始执行询价任务",
            extra={
                "action": "execute_quote_start",
                "quote_id": cast(int, quote.id),
                "preserve_amount": str(quote.preserve_amount),
                "corp_id": quote.corp_id,
                "category_id": quote.category_id,
                "credential_id": quote.credential_id,
                "status": quote.status,
            },
        )

        await self.repo.mark_running(quote=quote)

        try:
            token = await self.token_provider.get_token(quote.credential_id)
            companies = await self.client_facade.fetch_insurance_companies(
                token=token,
                category_id=quote.category_id,
                corp_id=quote.corp_id,
            )
            await self.repo.set_total_companies(quote=quote, total=len(companies))

            premium_results = await self.client_facade.fetch_all_premiums(
                token=token,
                preserve_amount=quote.preserve_amount,
                corp_id=quote.corp_id,
                companies=companies,
            )
            success_count, failed_count = await self.repo.save_premium_results(quote=quote, results=premium_results)

            error_message: str | None = None
            if success_count == 0:
                error_message = str(_("所有保险公司查询均失败"))

            await self.repo.finalize_quote(
                quote=quote,
                success_count=success_count,
                failed_count=failed_count,
                error_message=error_message,
            )

            execution_time = (
                (quote.finished_at - quote.started_at).total_seconds() if quote.finished_at and quote.started_at else 0
            )
            total_elapsed_time = time.time() - task_start_time

            logger.info(
                "✅ 询价任务执行完成",
                extra={
                    "action": "execute_quote_complete",
                    "quote_id": cast(int, quote.id),
                    "status": quote.status,
                    "total_companies": quote.total_companies,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "execution_time_seconds": round(execution_time, 2),
                    "total_elapsed_time_seconds": round(total_elapsed_time, 2),
                    "success_rate": (
                        round(success_count / quote.total_companies * 100, 2) if quote.total_companies > 0 else 0
                    ),
                },
            )

            return {
                "quote_id": cast(int, quote.id),
                "status": quote.status,
                "total_companies": quote.total_companies,
                "success_count": success_count,
                "failed_count": failed_count,
                "execution_time": execution_time,
            }
        except Exception as e:
            await self.repo.mark_failed(quote=quote, error_message=str(e))
            failed_elapsed_time = time.time() - task_start_time
            logger.error(
                f"❌ 询价任务执行失败: {e}",
                extra={
                    "action": "execute_quote_failed",
                    "quote_id": cast(int, quote.id),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "elapsed_time_seconds": round(failed_elapsed_time, 2),
                },
                exc_info=True,
            )
            raise

    async def retry_quote(self, quote_id: int) -> dict[str, Any]:
        quote = await self.repo.get_quote_model(quote_id=quote_id)

        if quote.status not in [QuoteStatus.FAILED, QuoteStatus.PARTIAL_SUCCESS]:
            logger.warning(
                "任务状态不允许重试",
                extra={
                    "action": "retry_quote_invalid_status",
                    "quote_id": cast(int, quote.id),
                    "current_status": quote.status,
                },
            )
            raise ValidationError(
                message=f"任务状态为 {quote.get_status_display()},不允许重试.只有失败或部分成功的任务可以重试.",
                errors={},
            )

        logger.info(
            "开始重试询价任务",
            extra={
                "action": "retry_quote_start",
                "quote_id": cast(int, quote.id),
                "previous_status": quote.status,
                "previous_success_count": quote.success_count,
                "previous_failed_count": quote.failed_count,
            },
        )

        await self.repo.reset_for_retry(quote=quote)
        return await self.execute_quote(quote_id)
