"""Strategy pattern implementations."""

from datetime import datetime

from apps.automation.services.document_delivery.data_classes import DocumentQueryResult
from typing import Any


class DocumentDeliveryPlaywrightStrategy:
    def __init__(self, *,  playwright_service: Any) -> None:
        self.playwright_service = playwright_service

    def query_and_download(
        self,
        *,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",
        debug_mode: bool = True,
    ) -> DocumentQueryResult:
        return self.playwright_service.query_documents(
            credential_id=credential_id, cutoff_time=cutoff_time, tab=tab, debug_mode=debug_mode
        )
