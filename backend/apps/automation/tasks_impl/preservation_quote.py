"""Module for preservation quote."""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.automation")


def execute_preservation_quote_task(quote_id: int) -> None:
    import asyncio

    from apps.automation.models import PreservationQuote, QuoteStatus
    from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
    from apps.automation.services.insurance.exceptions import TokenError
    from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
    from apps.automation.services.scraper.core.token_service import TokenServiceAdapter

    logger.info(f"🚀 开始执行询价任务 #{quote_id}")

    try:
        token_service = TokenServiceAdapter()
        insurance_client = CourtInsuranceClient(token_service)
        quote_service = PreservationQuoteService(token_service=token_service, insurance_client=insurance_client)

        result = asyncio.run(quote_service.execute_quote(quote_id))

        logger.info(f"✅ 询价任务 #{quote_id} 执行完成: {result}")
        return result  # type: ignore[return-value]

    except TokenError as e:
        logger.error(f"❌ 询价任务 #{quote_id} Token 错误: {e}")

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = f"Token 错误: {e!s}"
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error(f"更新任务状态失败: {update_error}")

        return {"quote_id": quote_id, "status": "failed", "error": "token_error", "message": str(e)}  # type: ignore[return-value]

    except Exception as e:
        logger.error(f"❌ 询价任务 #{quote_id} 执行失败: {e}", exc_info=True)

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error(f"更新任务状态失败: {update_error}")

        raise
