"""Strategy pattern implementations."""

from datetime import datetime
from typing import Protocol

from apps.automation.services.document_delivery.data_classes import DocumentQueryResult


class DocumentDeliveryQueryStrategy(Protocol):
    def query_and_download(
        self,
        *,
        credential_id: int,
        cutoff_time: datetime,
        tab: str = "pending",
        debug_mode: bool = True,
    ) -> DocumentQueryResult | None: ...
