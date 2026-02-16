"""Strategy pattern implementations."""

import traceback
from datetime import datetime

from apps.automation.utils.logging import AutomationLogger

from apps.automation.services.document_delivery.data_classes import DocumentQueryResult
from typing import Any
import logging

logger = logging.getLogger(__name__)


class DocumentDeliveryApiStrategy:
    def __init__(self, *,  token_service: Any, api_service: Any) -> None:
        self.token_service = token_service
        self.api_service = api_service

    def query_and_download(
        self,
        *,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",
        debug_mode: bool = True,
    ) -> DocumentQueryResult | None:
        try:
            token = self.token_service.acquire_token(credential_id)
            if not token:
                AutomationLogger.log_fallback_triggered(
                    from_method="api", to_method="playwright", reason="Token 获取失败", credential_id=credential_id
                )
                return None

            result = self.api_service.query_documents(token=token, cutoff_time=cutoff_time, credential_id=credential_id)
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found,
                processed_count=result.processed_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                query_method="api",
                credential_id=credential_id,
            )
            return result
        except Exception as e:
            logger.exception("操作失败")
            error_type = type(e).__name__
            error_msg = str(e)
            AutomationLogger.log_fallback_triggered(
                from_method="api",
                to_method="playwright",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id,
            )
            AutomationLogger.log_api_error_detail(
                api_name="document_query_api",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc(),
            )
            return None
